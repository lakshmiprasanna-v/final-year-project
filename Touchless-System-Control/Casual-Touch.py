import cv2
import HandTrackingModule as htm
import time
import pyautogui

class TouchlessController:
    def __init__(self):
        # Configuration Parameters
        self.wCam, self.hCam = 640, 480
        self.frameR = 90
        self.smoothening = 4
        self.clickCooldown = 0.45
        self.clickHoldTime = 0.18
        self.gestureHoldTime = 0.35
        self.pinchDistancePx = 30
        self.scrollDistancePx = 42
        self.scrollScale = 0.65
        self.scrollDeadzonePx = 2.0
        self.pinchReleasePx = 45
        self.pinchFramesRequired = 3
        self.lastActionLabel = "IDLE"
        self.debugPinchLen = -1
        self.debugPalmWidth = -1

        # Initialize Variables
        self.pTime = 0
        self.plocX, self.plocY = 0, 0
        self.clocX, self.clocY = 0, 0
        self.lastClickTime = 0
        self.prevScrollY = None
        self.scrollRemainder = 0.0
        self.pinchStableFrames = 0
        self.pinchActive = False

        self.gestureStates = {
            "move": {"startTime": 0, "active": False, "fired": False},
            "click": {"startTime": 0, "active": False, "fired": False},
            "rightClick": {"startTime": 0, "active": False, "fired": False},
        }

        self.detector = htm.handDetector(maxHands=1)
        try:
            self.wScr, self.hScr = pyautogui.size()
        except:
            self.wScr, self.hScr = 1920, 1080 # Default for testing/headless
        self.camera_index = None

    def _try_open_camera(self, idx):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(3, self.wCam)
        cap.set(4, self.hCam)
        ok, _ = cap.read()
        if ok:
            self.camera_index = idx
            return cap
        cap.release()
        return None

    def _open_camera(self):
        # Try common camera indexes and keep the first that returns frames.
        for idx in (0, 1, 2):
            cap = self._try_open_camera(idx)
            if cap is not None:
                return cap
        return None

    @staticmethod
    def _enhance_low_light(img):
        # Apply mild gain only when frame is very dark.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_luma = gray.mean()
        if mean_luma < 45:
            return cv2.convertScaleAbs(img, alpha=2.2, beta=30), True
        if mean_luma < 70:
            return cv2.convertScaleAbs(img, alpha=1.5, beta=15), True
        return img, False

    def _switch_camera(self, cap):
        next_idx = ((self.camera_index or 0) + 1) % 3
        start_idx = next_idx
        while True:
            new_cap = self._try_open_camera(next_idx)
            if new_cap is not None:
                cap.release()
                return new_cap
            next_idx = (next_idx + 1) % 3
            if next_idx == start_idx:
                break
        return cap

    @staticmethod
    def _interp(val, in_min, in_max, out_min, out_max):
        if in_max == in_min:
            return out_min
        ratio = (val - in_min) / (in_max - in_min)
        ratio = max(0.0, min(1.0, ratio))
        return out_min + ratio * (out_max - out_min)

    def updateGestureState(self, gestureName, condition, holdTime=None, repeat=True):
        currentTime = time.time()
        hold = self.gestureHoldTime if holdTime is None else holdTime
        state = self.gestureStates[gestureName]
        if condition:
            if not state["active"]:
                state["startTime"] = currentTime
                state["active"] = True
                state["fired"] = False
            else:
                enough_hold = currentTime - state["startTime"] >= hold
                if enough_hold and (repeat or not state["fired"]):
                    if repeat:
                        state["startTime"] = currentTime
                    else:
                        state["fired"] = True
                    return True
        else:
            state["active"] = False
            state["fired"] = False
        return False

    def processGesture(self, fingers, x1, y1, x2, y2, img):
        self.lastActionLabel = "IDLE"

        # Move cursor
        if fingers[1] == 1 and all(fingers[i] == 0 for i in range(2, 5)):
            x3 = self._interp(x1, self.frameR, self.wCam - self.frameR, 0, self.wScr)
            y3 = self._interp(y1, self.frameR, self.hCam - self.frameR, 0, self.hScr)
            self.clocX = self.plocX + (x3 - self.plocX) / self.smoothening
            self.clocY = self.plocY + (y3 - self.plocY) / self.smoothening

            try:
                pyautogui.moveTo(self.wScr - self.clocX, self.clocY)
            except pyautogui.FailSafeException:
                pass

            cv2.circle(img, (x1, y1), 15, (255, 0, 255), cv2.FILLED)
            self.plocX, self.plocY = self.clocX, self.clocY
            self.lastActionLabel = "MOVE"

        # Click and Scroll with index+middle gesture
        if fingers[1] == 1 and fingers[2] == 1:
            length, img, lineInfo = self.detector.findDistance(8, 12, img)
            self.debugPinchLen = int(length)

            # Adaptive thresholds from palm width (landmarks 5-17).
            # Keep upper bounds conservative so scroll mode remains reachable.
            palm_len, _, _ = self.detector.findDistance(5, 17, img, draw=False)
            self.debugPalmWidth = int(palm_len)
            dynamic_pinch = max(18, min(34, int(0.24 * palm_len)))
            dynamic_release = dynamic_pinch + 10
            dynamic_scroll = dynamic_release + 4

            if length < dynamic_pinch:
                self.prevScrollY = None
                self.scrollRemainder = 0.0
                self.pinchStableFrames += 1
                if (
                    self.pinchStableFrames >= self.pinchFramesRequired
                    and not self.pinchActive
                    and (time.time() - self.lastClickTime) > self.clickCooldown
                ):
                    cv2.circle(img, (lineInfo[4], lineInfo[5]), 15, (0, 255, 0), cv2.FILLED)
                    try:
                        pyautogui.click()
                    except pyautogui.FailSafeException:
                        pass
                    self.lastClickTime = time.time()
                    self.pinchActive = True
                    self.lastActionLabel = "CLICK"
            elif length > dynamic_release:
                self.pinchStableFrames = 0
                self.pinchActive = False
                self.updateGestureState("click", False)
                if length >= dynamic_scroll:
                    currentY = (y1 + y2) / 2
                    if self.prevScrollY is not None:
                        delta = self.prevScrollY - currentY
                        if abs(delta) >= self.scrollDeadzonePx:
                            self.scrollRemainder += delta * self.scrollScale
                        scroll_amount = int(self.scrollRemainder)
                        if scroll_amount != 0:
                            try:
                                pyautogui.scroll(scroll_amount)
                            except pyautogui.FailSafeException:
                                pass
                            self.scrollRemainder -= scroll_amount
                            self.lastActionLabel = f"SCROLL {scroll_amount}"
                    self.prevScrollY = currentY
            else:
                # In-between pinch/release range: keep previous state (hysteresis).
                pass
            self.pinchDistancePx = dynamic_pinch
            self.pinchReleasePx = dynamic_release
            self.scrollDistancePx = dynamic_scroll
        else:
            self.updateGestureState("click", False)
            self.prevScrollY = None
            self.scrollRemainder = 0.0
            self.pinchStableFrames = 0
            self.pinchActive = False
            self.debugPinchLen = -1
            self.debugPalmWidth = -1

        # Right Click
        if self.updateGestureState("rightClick", all(fingers[i] == 1 for i in range(1, 5)), repeat=False):
            try:
                pyautogui.rightClick()
            except pyautogui.FailSafeException:
                pass
            self.lastActionLabel = "RIGHT_CLICK"

    def run(self):
        cap = self._open_camera()
        if cap is None:
            print("Error: Camera not accessible")
            return

        while True:
            success, img = cap.read()
            if not success:
                print("Failed to capture image")
                continue

            img, low_light = self._enhance_low_light(img)

            img = self.detector.findHands(img)
            lmList, bbox = self.detector.findPosition(img)

            if len(lmList) != 0:
                x1, y1 = lmList[8][1:]
                x2, y2 = lmList[12][1:]
                fingers = self.detector.fingersUp()
                cv2.rectangle(img, (self.frameR, self.frameR), (self.wCam - self.frameR, self.hCam - self.frameR), (255, 0, 255), 2)

                # Process gestures
                self.processGesture(fingers, x1, y1, x2, y2, img)
            else:
                cv2.putText(img, "No hand detected", (20, 90), cv2.FONT_HERSHEY_PLAIN, 2, (0, 200, 255), 2)

            # Frame Rate
            cTime = time.time()
            dt = max(cTime - self.pTime, 1e-6)
            fps = 1 / dt
            self.pTime = cTime
            cv2.putText(img, f"FPS: {int(fps)}", (20, 50), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
            cv2.putText(img, f"Cam: {self.camera_index}", (20, 120), cv2.FONT_HERSHEY_PLAIN, 2, (200, 255, 0), 2)
            cv2.putText(img, "Press q to quit", (20, 150), cv2.FONT_HERSHEY_PLAIN, 2, (220, 220, 220), 2)
            cv2.putText(img, "Press c to switch cam", (20, 180), cv2.FONT_HERSHEY_PLAIN, 2, (220, 220, 220), 2)
            cv2.putText(img, "Press k for test click", (20, 210), cv2.FONT_HERSHEY_PLAIN, 2, (220, 220, 220), 2)
            if low_light:
                cv2.putText(img, "Low light mode active", (20, 240), cv2.FONT_HERSHEY_PLAIN, 2, (0, 165, 255), 2)
            cv2.putText(img, f"Action: {self.lastActionLabel}", (20, 270), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)
            if self.debugPinchLen >= 0:
                dbg = f"Pinch:{self.debugPinchLen}px Th:{self.pinchDistancePx}/{self.pinchReleasePx} Palm:{self.debugPalmWidth}px"
                cv2.putText(img, dbg, (20, 300), cv2.FONT_HERSHEY_PLAIN, 1, (255, 255, 255), 1)

            # Display
            cv2.imshow("Image", img)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            if key == ord('c'):
                new_cap = self._switch_camera(cap)
                if new_cap is not None:
                    cap = new_cap
            if key == ord('k'):
                try:
                    pyautogui.click()
                    self.lastActionLabel = "TEST_CLICK"
                except pyautogui.FailSafeException:
                    self.lastActionLabel = "TEST_CLICK_FAILSAFE"

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    controller = TouchlessController()
    controller.run()
