import json
import unittest
from unittest.mock import patch
from karmazyn_comm import termux_sms_list

class TestTermuxSmsList(unittest.TestCase):

    @patch('karmazyn_comm._run')
    def test_termux_sms_list_success(self, mock_run):
        mock_data = [{"_id": 1, "body": "test"}]
        mock_run.return_value = (0, json.dumps(mock_data), "")
        result = termux_sms_list(limit=10)
        self.assertEqual(result, mock_data)
        mock_run.assert_called_once_with(["termux-sms-list", "-l", "10", "-t", "inbox"])

    @patch('karmazyn_comm._run')
    def test_termux_sms_list_error_code(self, mock_run):
        mock_run.return_value = (1, "some error", "error")
        result = termux_sms_list()
        self.assertEqual(result, [])

    @patch('karmazyn_comm._run')
    def test_termux_sms_list_empty_out(self, mock_run):
        mock_run.return_value = (0, "", "")
        result = termux_sms_list()
        self.assertEqual(result, [])

    @patch('karmazyn_comm._run')
    def test_termux_sms_list_invalid_json(self, mock_run):
        mock_run.return_value = (0, "{invalid json}", "")
        result = termux_sms_list()
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
