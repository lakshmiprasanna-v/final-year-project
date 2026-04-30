import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import importlib.util

# Mock dependencies before importing the module
sys.modules['HandTrackingModule'] = MagicMock()
sys.modules['cv2'] = MagicMock() # Mock OpenCV
# Mock pyautogui but keep it available for assertions
mock_pyautogui = MagicMock()
sys.modules['pyautogui'] = mock_pyautogui

# Helper to import the modified script
def import_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Import Casual-Touch
file_path = os.path.join(os.path.dirname(__file__), 'Casual-Touch.py')
casual_touch = import_from_path('CasualTouch', file_path)

class TestTouchlessFeatures(unittest.TestCase):
    def setUp(self):
        self.controller = casual_touch.TouchlessController()
        self.controller.detector = MagicMock()
        # Default behavior for findDistance (return large length to avoid accidental clicks)
        self.controller.detector.findDistance.return_value = (100, MagicMock(), [0, 0, 0, 0, 0, 0])
        # Ensure config matches defaults
        self.controller.wScr = 1920
        self.controller.hScr = 1080
        # Reset mocks
        mock_pyautogui.reset_mock()
        
    def test_move_cursor(self):
        """Test if cursor move logic calculates coordinates and calls moveTo."""
        # Fingers: Index (1) up, others down
        fingers = [0, 1, 0, 0, 0]
        # Coordinates: x1, y1 (Index tip)
        x1, y1 = 200, 200
        x2, y2 = 0, 0 # Middle finger, irrelevant for move
        img = MagicMock()

        with patch('time.time') as mock_time:
            mock_time.return_value = 1000.0
            self.controller.processGesture(fingers, x1, y1, x2, y2, img)

        mock_pyautogui.moveTo.assert_called()
            
    def test_click(self):
        """Test click logic."""
        # Fingers: Index (1) and Middle (1) up
        fingers = [0, 1, 1, 0, 0]
        x1, y1 = 0, 0 
        x2, y2 = 0, 0
        img = MagicMock()
        
        # Keep pinch distance below adaptive threshold.
        self.controller.detector.findDistance.return_value = (15, img, [0] * 6)
        
        with patch('time.time') as mock_time:
            mock_time.return_value = 2000.0
            self.controller.processGesture(fingers, x1, y1, x2, y2, img)
            mock_pyautogui.click.assert_not_called()

            mock_time.return_value = 2000.1
            self.controller.processGesture(fingers, x1, y1, x2, y2, img)
            mock_pyautogui.click.assert_not_called()

            mock_time.return_value = 2000.2
            self.controller.processGesture(fingers, x1, y1, x2, y2, img)
            mock_pyautogui.click.assert_called()
            
    def test_scroll(self):
        """Test scroll logic."""
        fingers = [0, 1, 1, 0, 0]
        # Distance >= 40
        self.controller.detector.findDistance.return_value = (50, MagicMock(), [0]*6)

        # First frame initializes scroll baseline.
        self.controller.processGesture(fingers, 0, 200, 0, 300, MagicMock())
        mock_pyautogui.scroll.assert_not_called()

        # Move hand up (reduced y) should yield positive scroll.
        self.controller.processGesture(fingers, 0, 100, 0, 200, MagicMock())
        expected = int(100 * self.controller.scrollScale)
        mock_pyautogui.scroll.assert_called_with(expected)
        self.assertTrue(self.controller.lastActionLabel.startswith("SCROLL "))

    def test_scroll_accumulates_small_motion(self):
        """Small frame deltas should accumulate into scroll steps."""
        fingers = [0, 1, 1, 0, 0]
        self.controller.detector.findDistance.return_value = (50, MagicMock(), [0]*6)

        # Baseline: currentY=250
        self.controller.processGesture(fingers, 0, 200, 0, 300, MagicMock())
        mock_pyautogui.scroll.assert_not_called()

        # Delta=1 (below deadzone), still no scroll.
        self.controller.processGesture(fingers, 0, 199, 0, 299, MagicMock())
        mock_pyautogui.scroll.assert_not_called()

        # Delta=3 should accumulate enough for one scroll step.
        self.controller.processGesture(fingers, 0, 196, 0, 296, MagicMock())
        mock_pyautogui.scroll.assert_called_with(1)

    def test_right_click(self):
        """Test right click logic."""
        # Fingers: 1, 2, 3, 4 up. Thumb (0) doesn matter?
        # Code: all(fingers[i] == 1 for i in range(1, 5)) -> Index, Middle, Ring, Pinky
        fingers = [0, 1, 1, 1, 1]
        
        with patch('time.time') as mock_time:
            mock_time.return_value = 3000.0
            # First call activates
            self.controller.processGesture(fingers, 0, 0, 0, 0, MagicMock())
            mock_pyautogui.rightClick.assert_not_called()
            
            # Wait
            mock_time.return_value = 3000.0 + 1.0
            self.controller.processGesture(fingers, 0, 0, 0, 0, MagicMock())
            mock_pyautogui.rightClick.assert_called()

if __name__ == '__main__':
    unittest.main()
