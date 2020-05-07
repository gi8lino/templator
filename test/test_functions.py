import copy
import json
import os
import sys
import unittest
from io import StringIO
from unittest import mock
from contextlib import contextmanager

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))


import templator


@contextmanager
def captured_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class TestSum(unittest.TestCase):

    def tearDown(self):
        mock.patch.stopall()

    def test_parse_args(self):
        # no args (no path given)
        with captured_output() as (out, err):
            with self.assertRaises(SystemExit) as cm:
                templator.parse_args()
            self.assertEqual(cm.exception.code, 2)
            outerr = err.getvalue()
            self.assertIn("the following arguments are required", outerr)

        # unknown paramters
        with captured_output() as (out, err):
            args = ["templator.py", "template.txt", "--test"]
            with mock.patch('sys.argv', args), self.assertRaises(SystemExit):
                templator.parse_args()
            self.assertIn(
                "templator.py: error: unrecognized argument", err.getvalue())

        # --delemiter-in-file, but no --input
        with captured_output() as (out, err):
            args = ["templator.py", "template.txt", "-d", "="]
            with mock.patch('sys.argv', args), self.assertRaises(SystemExit):
                templator.parse_args()
            outerr = err.getvalue()
            self.assertIn(
                "templator.py: error: you cannot set a delimiter", outerr)

        # -d|--delemiter-in-file, set --input
        args = ["templator.py", "template.txt", "-d", "=", "-i", "intput.env"]
        with mock.patch('sys.argv', args):
            templator.parse_args()

        # -a|--append, no --input
        with captured_output() as (out, err):
            args = ["templator.py", "template.txt", "-a"]
            with mock.patch('sys.argv', args), self.assertRaises(SystemExit):
                templator.parse_args()
        outerr = err.getvalue()
        self.assertIn("-a|--append", outerr)

        # -f|--force, no --input
        with captured_output() as (out, err):
            args = ["templator.py", "template.txt", "-f"]
            with mock.patch('sys.argv', args), self.assertRaises(SystemExit):
                templator.parse_args()
        outerr = err.getvalue()
        self.assertIn("-f|--force", outerr)

        # a|--append & -f|--force, no --input
        with captured_output() as (out, err):
            args = ["templator.py", "template.txt", "-f", "-a"]
            with mock.patch('sys.argv', args), self.assertRaises(SystemExit):
                templator.parse_args()
            outerr = err.getvalue()
            self.assertIn("'-a|--append' and/or '-f|--force'", outerr)

        # -a|--append, set --input
        args = ["templator.py", "template.txt", "-a", "-o", "dst/"]
        with mock.patch('sys.argv', args):
            templator.parse_args()

        # -f|--force, set --output
        args = ["templator.py", "template.txt", "-a", "-o", "dst/"]
        with mock.patch('sys.argv', args):
            templator.parse_args()

        # -a|--append & -f|--force, set --output
        args = ["templator.py", "template.txt", "-a", "-o", "dst/"]
        with mock.patch('sys.argv', args):
            templator.parse_args()

    def test_skip_path(self):
        path = "path/dir/file.md"

        # no excludes
        self.assertFalse(templator.skip_path(path=path))

        # exclude dir found
        excludes = ['test', 'dir']
        self.assertTrue(templator.skip_path(path=path, excludes=excludes))

        # exclude dir found
        excludes = ['test', 'file.md']
        self.assertTrue(templator.skip_path(path=path, excludes=excludes))

        # exclude dir not found
        excludes = ['test', 'test2']
        self.assertFalse(templator.skip_path(path=path, excludes=excludes))

        # exclude extension found
        excludes = ['test', '.md']
        self.assertTrue(templator.skip_path(path=path, excludes=excludes))

        # exclude extension found
        excludes = ['test', '*.md']
        self.assertTrue(templator.skip_path(path=path, excludes=excludes))

        # exclude extension not found
        excludes = ['test', '.txt']
        self.assertFalse(templator.skip_path(path=path, excludes=excludes))

        # exclude extension not found
        excludes = ['test', '*.txt']
        self.assertFalse(templator.skip_path(path=path, excludes=excludes))

    def test_out_file(self):

        patcher = mock.patch('templator.parse_template')
        mock_parse_template = patcher.start()

        # src = dst
        with self.assertRaises(SyntaxError) as cm:
            templator.output_file(src="src", dst="src")

        # output to console
        src_content = "line 1\nline 2\nline3\n"
        with captured_output() as (out, err):
            mock_parse_template.return_value = src_content
            templator.output_file(src="src")
        out = out.getvalue()
        dst_content = f"{src_content}\n"
        self.assertEqual(out, dst_content)

        # file exists
        with captured_output() as (out, err):
            with mock.patch('os.path.exists') as cm:
                cm.return_value = True
                templator.output_file(src="src", dst="test.txt")

        outerr = err.getvalue()
        self.assertIn("'test.txt' already exists", outerr)

        patcher = mock.patch('os.path.exists')
        mock_path_mkdir = patcher.start()
        mock_path_mkdir.return_value = False

        # cannot create dir
        with mock.patch('pathlib.Path.mkdir') as mock_mkdir:
            e = Exception()
            setattr(e, "strerror", "error")
            mock_mkdir.side_effect = e
            with self.assertRaises(Exception) as err:
                templator.output_file(src="src", dst="test.txt")

            self.assertIn("cannot create directory", str(err.exception))

    def test_parse_template(self):
        with self.assertRaises(FileNotFoundError) as cm:
            templator.parse_template(template="test.yaml",
                                     substitutions=[])

        patcher = mock.patch('os.path.isfile')
        mock_path_is_file = patcher.start()
        mock_path_is_file.return_value = True

        # open
        path = "test.yaml"
        src_content = "line 1\nline 2\nline3"
        mock_open = mock.mock_open(read_data=src_content)
        with mock.patch("builtins.open", mock_open):
            processed_content = templator.parse_template(template=path,
                                                         substitutions=[])
        self.assertEqual(src_content, processed_content)

    def test_print_diff(self):
        templates = [
            {
                'original': "line 1\nline 2\nline 3\nline4",
                'new': "line 2\nline 3\nline4",
                'results': ["line 1"],
            },
            {
                'original': "line 1\nline 2\nline 3\nline4",
                'new': "line 1\nline 3\nline4",
                'results': ["line2"],
            },
            {
                'original': "line 1\nline 2\nline 3\nline4",
                'new': "line 1\nline 2\nline 3",
                'results': ["line 4"],
            },
            {
                'original': "line 1\nline 2\nline 3\nline4",
                'new': "line 1\nline4",
                'results': ["line 2", "line3"],
            },
        ]
        for template in templates:
            with captured_output() as (out, err):
                templator.print_diff(
                    template_name="test",
                    original_content=template['original'],
                    new_content=template['new'])
                out = out.getvalue()
                for result in template['results']:
                    self.assertIn(result, template['results'])

    def test_read_key_value_list(self):
        with self.assertLogs() as logs:
            templator.read_key_value_list(key_value_list=["key: value"])
            self.assertIn("has no valid delimiter", logs.output[0])

        with self.assertLogs() as logs:
            templator.read_key_value_list(key_value_list=["=value"])
            self.assertIn("cannot get key from", logs.output[0])

        with self.assertLogs() as logs:
            templator.read_key_value_list(key_value_list=["key="])
            self.assertIn("cannot get value from", logs.output[0])

        with self.assertRaises(KeyError) as logs:
            templator.read_key_value_list(
                key_value_list=["key=value", "key=value"])
            self.assertIn("you cannot pass the same key", cm.exception)

    def test_read_file(self):
        # file not found
        with self.assertRaises(FileNotFoundError) as exc:
            templator.read_file(
                path="test.env",
                delimiter=None)

        patcher = mock.patch('os.path.isfile')
        mock_path_exists = patcher.start()
        mock_path_exists.return_value = True

        for delimiter in ['=', ':']:
            items = [
                {
                    'data': "BASE_DOMAIN"
                            f"{':' if delimiter == '=' else '='}"
                            "example.com\n",
                    'path': "test.env",
                    'result': "no valid delimiter"
                },
                {
                    'data': f"{delimiter}value",
                    'path': "test.env",
                    'result': "cannot get key from line"
                },
                {
                    'data': f"key{delimiter}",
                    'path': "test.env",
                    'result': "cannot get value from line"
                },
                {
                    'data': f"key{delimiter}value\nkey{delimiter}value",
                    'path': "test.env",
                    'result': "already set"
                },
            ]

        for item in items:
            with self.assertLogs() as logs:
                mock_open = mock.mock_open(read_data=item['data'])
                with mock.patch("builtins.open", mock_open):
                    templator.read_file(
                        path=item['path'],
                        delimiter=delimiter)
                    self.assertIn(item['result'], logs.output[0])

        with self.assertRaises(TypeError) as context:
            templator.read_file(
                path="test.txt",
                delimiter=None)
            self.assertIn("does not end with", context.exception)

    def test_find_vars(self):
        contents = [
            {
                'txt': "",
                'len': 0
            },
            {
                'txt': "line 1\nline 2\nline 3\nline 4",
                'len': 0
            },
            {
                'txt': "line 1\nline 2\n $VAR\nline 4",
                'len': 1
            },
            {
                'txt': "line 1\nline 2\n ${VAR}\nline 4",
                'len': 1
            },
            {
                'txt': "line 1\n$VAR\n ${VAR}\nline 4",
                'len': 2
            },
            {
                'txt': "line 1\n$VAR\n ${VAR}\nline 4\n$VAR\${VAR}",
                'len': 4
            },
        ]
        for content in contents:
            result = templator.find_vars(text=content['txt'])
            self.assertEqual(len(result), content['len'])


if __name__ == '__main__':
    unittest.main()
