#!/usr/bin/env python3
import argparse
import difflib
import json
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path
from string import Template

__version__ = "v1.0.1"
__author__ = "gi8lino"

# colors
BOLD = '\033[1m'
ITALIC = '\33[3m'
UNDERLINE = '\033[4m'
DEFAULT = '\033[0m'  # no color / no format

pattern = re.compile(r"(?<!\$)(\$[a-zA-Z0-9_]+|\${[a-zA-Z0-9_]+})")


class CustomHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog):
        # change max_help_position
        super(CustomHelpFormatter, self).__init__(prog, max_help_position=42)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts = []
            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, format is:
            #    -s, --long ARGS
            else:
                default = action.dest.upper()
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append('%s' % option_string)
                parts[-1] += ' %s' % args_string
            return ', '.join(parts)


class CustomFormatter(CustomHelpFormatter,
                      argparse.RawDescriptionHelpFormatter):
    pass


class ColorStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        class AddColor(logging.Formatter):
            def format(self, record: logging.LogRecord):
                msg = super().format(record)
                # Cyan/Green/Yellow/Red/Redder based on log level:
                color = '\x1b[' + ('36m', '32m', '33m', '31m', '41m')[
                   min(4, int(4 * record.levelno / logging.FATAL))]
                return color + record.levelname.ljust(7) + '\x1b[0m: ' + msg

        class InfoFilter(logging.Filter):
            def filter(self, rec):
                return rec.levelno in (logging.DEBUG, logging.INFO)

        super().__init__(*args, **kwargs)

        if self.stream == sys.stdout:
            self.setLevel(logging.DEBUG)
            self.addFilter(InfoFilter())
        elif self.stream == sys.stderr:
            self.setLevel(logging.WARNING)

        self.setFormatter(AddColor())


def parse_args() -> argparse.Namespace:
    """parse known args and return argparse.Namespace"""
    parser = argparse.ArgumentParser(
        formatter_class=CustomFormatter,
        add_help=False,
        description="""
Replace all instances of $VAR and/or ${VAR} in a file with the
corresponding passed values and send the result to stdout or to a file.

Variables can be passed as followed:
- directly with key=value pairs (parameter '-s KEY1=VALUE1 [KEY2=VALUE2 ...]')
- from .json and/or .env files (parameter '-i PATH [PATH ...]')
- from os environment variables (can be disabled with parameter '--no-os-env')
""",
        epilog=(
            f"{BOLD}Supported variable types{DEFAULT}:\n\n"
            """
Supports $-based substitutions, using the following rules:
- "$$" is an escape; it is replaced with a single "$".
- "$identifier" names a substitution placeholder matching a mapping key of
  "identifier". By default, "identifier" is restricted to any case-insensitive
  ASCII alphanumeric string (including underscores) that starts with an
  underscore or ASCII letter. The first non-identifier character after the
  "$" character terminates this placeholder specification.
- "${identifier}" is equivalent to "$identifier". It is required when valid
  identifier characters follow the placeholder but are not part of the
  placeholder, such as "${noun}ification".
            """
            f"\n{BOLD}replacement order:{DEFAULT}\n\n"
            "The order of replacing variables is:\n"
            f"- directly passed key=value pairs ('-s') {BOLD}*{DEFAULT}\n"
            f"- input files ('-i') {BOLD}*{DEFAULT}\n"
            f"- os environment variables (can be disabled with"
            "   parameter '--no-os-env')"
            f"\n\n{BOLD}*{DEFAULT}{ITALIC}in order you pass them to the "
            f"script{DEFAULT}\n\n"
            "see full documentation here: https://github.com/gi8lino/templator"
        )
    )
    parser.add_argument(action="store",
                        dest="src",
                        nargs='+',
                        metavar="PATH",
                        help="path to template file or directory containing"
                             " template files")
    parser.add_argument("--diff",
                        action="store_true",
                        dest="diff",
                        default=None,
                        help="show replaced lines")
    parser.add_argument("-r", "--recursive",
                        action="store_true",
                        dest="recursive",
                        default=None,
                        help="process templates directory recursively")
    parser.add_argument("-e", "--exclude",
                        action="store",
                        dest="excludes",
                        metavar="STRING",
                        nargs='+',
                        help="exclude path containing [STRING]")
    parser.add_argument("--strict",
                        action="store_true",
                        dest="strict",
                        default=None,
                        help=f"raise an error if not {UNDERLINE}all{DEFAULT}"
                             " variables could be replaced")
    group_verbose = parser.add_mutually_exclusive_group(required=False)
    group_verbose.add_argument("--debug",
                               action="store_true",
                               dest="debug",
                               default=None,
                               help="set log level to debug")
    group_verbose.add_argument("-q", "--quiet",
                               action="store_true",
                               dest="quiet",
                               default=None,
                               help="do not output log")
    parser.add_argument("-v", "--version",
                        action="version",
                        version=f"templater version {__version__}\n"
                                f"by {__author__}",
                        help="show version number and exit")
    parser.add_argument('-h', '--help',
                        action='help',
                        default=argparse.SUPPRESS,
                        help='show this help message and exit')
    group_key_values = parser.add_argument_group("optional: set key=value")
    group_key_values.add_argument("-s", "--set",
                                  dest="key_value_list",
                                  nargs='*',
                                  metavar="KEY=VALUE",
                                  help="pass key=value pairs as variable")
    group_input = parser.add_argument_group("optional: input file")
    group_input.add_argument("-i", "--input",
                             dest="input_files",
                             nargs='+',
                             metavar="PATH",
                             help="files containing variable(s)")
    group_input.add_argument("-d", "--delimiter-in-file",
                             action="store",
                             dest="delimiter",
                             default=None,
                             help="set delimiter for key/value pairs in "
                                  f"{UNDERLINE}files{DEFAULT}. "
                                  "default: =")
    group_env = parser.add_argument_group("optional: read os environment")
    group_env.add_argument("-n", "--no-os-env",
                           action="store_true",
                           dest="no_os_env",
                           default=False,
                           help="do not use os environment")
    group_output = parser.add_argument_group("optional output")
    group_output.add_argument("-o", "--output",
                              action="store",
                              dest="dst",
                              metavar="PATH",
                              help="redirect output to file or a directory")
    group_output.add_argument("-a", "--append",
                              action="store_true",
                              dest="append",
                              default=None,
                              help="append to output file PATH")
    group_output.add_argument("-f", "--force",
                              action="store_true",
                              dest="force",
                              default=None,
                              help="replace existing output file")

    args, unknown = parser.parse_known_args()

    if unknown:
        parser.print_usage()
        sys.stderr.write("templator.py: error: unrecognized argument"
                         f"{'s' if len(unknown) != 1 else ''}: "
                         "'{0}'".format(
                             "', '".join(unknown)))
        sys.exit(1)

    if args.delimiter and not args.input_files:
        parser.print_usage()
        sys.stderr.write("templator.py: error: you cannot set a delimiter "
                         f"({args.delimiter}) without minimum one "
                         "input file\n")
        sys.exit(1)

    if (args.append or args.force) and not args.dst:
        errs = [
            "'-a|--append'" if args.append else None,
            "'-f|--force'" if args.force else None,
        ]
        parser.print_usage()
        sys.stderr.write("templator.py: error: you cannot set "
                         f"{' and/or '.join(filter(None, errs))}"
                         " without the parameter '-o|--output'\n")
        sys.exit(1)

    return args


def setup_logger(debug=False):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    stdout_handler = ColorStreamHandler(sys.stdout)
    stderr_handler = ColorStreamHandler(sys.stderr)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


def process(src: list,
            dst: str = None,
            show_diff: bool = False,
            recursive: bool = False,
            key_value_list: list = [],
            input_files: list = [],
            file_delimiter: str = '=',
            no_os_env: bool = True,
            strict: bool = False,
            append: bool = False,
            force: bool = False,
            excludes: list = []):

    dst = Path(dst) if dst else None

    parsed_key_value_list, parsed_files_vars, os_env = {}, {}, {}

    if key_value_list:
        parsed_key_value_list = read_key_value_list(
                                    key_value_list=key_value_list,
                                    delimiter='=')
    if input_files:
        for input_file in input_files:
            parsed_files_vars.update(read_file(
                path=input_file,
                delimiter=file_delimiter)
            )
    if not no_os_env:
        os_env_vars = os.environ

    substitutions = [
        parsed_key_value_list,
        parsed_files_vars,
        os_env_vars,
    ]

    for item in src:
        dst_dir = True if item.endswith("/") else False
        item = Path(item).expanduser()

        if not item.exists():
            raise LookupError(f"'{str(item)}' not found")

        if (dst and
           (not dst.is_dir() and not dst.is_file()) and
           (item.is_dir() or len(src) > 1) and
           not append):
            raise SyntaxError("you cannot add multiple templates and only one "
                              "destination file without parameter "
                              "'-a|--append'")

        try:
            if item.is_file():
                dst_file = (None if not dst else
                            dst if dst.suffix else
                            dst.joinpath("/".join(item.parts[-1:])))
                if skip_path(path=item, excludes=excludes):
                    continue
                output_file(src=item,
                            dst=dst_file,
                            append=append,
                            force=force,
                            substitutions=substitutions,
                            strict=strict,
                            show_diff=show_diff)
                continue

            item_parts = len(item.parts) if dst_dir else len(item.parts) - 1
            for i in item.glob('**/*' if recursive else '*'):
                if i.is_dir():
                    continue
                if skip_path(path=i, excludes=excludes):
                    continue
                dst_file = None
                if dst:
                    parts = i.parts[item_parts:]
                    dst_file = dst.joinpath("/".join(parts))
                    dst_file = dst_file if not dst.suffix else dst
                output_file(src=i,
                            dst=dst_file,
                            append=append,
                            force=force,
                            substitutions=substitutions,
                            strict=strict,
                            show_diff=show_diff)

        except Exception as e:
            logging.error(e)


def skip_path(path: str, excludes: list = []) -> bool:
    """search in path a string

    Arguments:
        path {str} -- string to be searched

    Keyword Arguments:
        excludes {list} -- list with string to compare with path (default: [])

    Returns:
        [bool] -- True if path contains entry of excludes else False
    """
    if not excludes:
        return False
    path = Path(path)
    # exclude is in file extension or in path
    excluded = [entry for entry in excludes if
                entry in path.parts or entry.lstrip('*') == path.suffix]
    if excluded:
        logging.debug(f"skip file '{path}' because of "
                      "'{VARS}'".format(VARS="', '".join(excluded)))
        return True
    return False


def output_file(src: str,
                dst: str = None,
                append: bool = False,
                force: bool = False,
                substitutions: list or dict = None,
                strict: bool = False,
                show_diff: bool = False):
    """parse template and send it to stdout. if dst defined, save to file

    Arguments:
        src {str} -- path to template

    Keyword Arguments:
        dst {str} -- path to save (default: {None})
        append {bool} -- if dst file exists, append template (default: {False})
        force {bool} -- overwrite existing dst file (default: {False})
        substitutions {list}/{dict} -- dict or list of dicts with keys that
                                       match the placeholders in the template
                                       (default: None)
        strict {bool} -- stop processing if not all variables could
                         be replaced (default: {False})
        show_diff {bool} - show replaced files

    Raises:
        SyntaxError: source and destination is equal
        Exception: cannot write file
    """

    if dst and src == dst:
        raise SyntaxError("source and destination cannot be equal!")

    content = parse_template(template=src,
                             substitutions=substitutions,
                             strict=strict,
                             show_diff=show_diff)
    if not dst:
        sys.stdout.flush()
        sys.stdout.write(f"{content}\n")
        return

    if os.path.exists(dst) and not append and not force:
        logging.warning(f"file '{dst}' already exists")
        return

    try:
        dst_parent = Path(dst).parent
        dst_parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise OSError(
                f"cannot create directory '{dst_parent}'. {e.strerror}")

    try:
        mode = f"{'append' if os.path.exists(dst) and append else 'save'}"
        with open(str(dst), "a" if append and not force else "w") as output:
            output.write(f"{content}\n")
        logging.info(f"{mode} "
                     f"template to '{dst}'")
    except Exception as e:
        raise Exception(f"cannot write file '{dst}'. {str(e)}")


def parse_template(template: str,
                   substitutions: list or dict = None,
                   strict: bool = False,
                   show_diff: bool = False) -> str:
    """replace $VAR / ${VAR} in a file

    Arguments:
        templates {str} -- path to templates

    Keyword Arguments:
        substitutions {list} or {dict} -- dict or list of dicts with keys that
                                       match the placeholders in the template
                                       (default: None)
        strict {bool} -- raise an LookupError if not all variables could
                         be replaced (default: {False})
        show_diff {bool} - show replaced files

    Raises:
        FileNotFoundError: template file not found
        LookupError: 'strict' option set and not all variables replaced
    """
    def substitute_vars(content: str, var_list: list or dict) -> str:
        if not var_list:
            return content
        if isinstance(var_list, dict):
            return Template(content).safe_substitute(item)
        if not isinstance(var_list, list):
            raise AttributeError(
                    "you only can pass a {dict} or a list of dicts")
        for item in var_list:
            if not item:
                continue
            if isinstance(item, list):
                substitute_vars(content=content, var_list=item)
                continue
            content = Template(content).safe_substitute(item)
        return content

    if not os.path.isfile(template):
        raise FileNotFoundError(f"template '{template}' not found")

    try:
        with open(file=template, mode="r") as data:
            original_content = data.read()

        logging.debug(f"parse template '{template}'")

        found_variables = find_vars(text=original_content)
        found_variable_len = len(found_variables)
        found_variable_joined = "'{0}'".format("', '".join(found_variables))

        logging.debug(
            f"found {found_variable_len} variable"
            f"{'s' if found_variable_len != 1 else ''}"
            f"{'!' if found_variable_len == 0 else ': '}"
            f"{'' if not found_variable_len else found_variable_joined}")

        content = substitute_vars(content=original_content,
                                  var_list=substitutions)

        unprocessed_vars = find_vars(text=content)
        unprocessed_vars_len = len(unprocessed_vars)
        unprocessed_vars_joined = "'{0}'".format("', '".join(unprocessed_vars))
        msg = (
            f"{found_variable_len - unprocessed_vars_len}/{found_variable_len}"
            " variable"
            f"{'s' if found_variable_len - unprocessed_vars_len != 1 else ''}"
            f" replaced{'!' if not unprocessed_vars_len else '.'}"
            f"{'' if not unprocessed_vars_len else  'Remaining variables: '}"
            f"{'' if not unprocessed_vars_len else unprocessed_vars_joined}"
        )

        if show_diff:
            if (not found_variable_len or
               found_variable_len == unprocessed_vars_len):
                logging.warning(
                    f"no lines in file '{template}' replaced!")
            else:
                logging.info(f"replaced lines in file '{template}'")
                print_diff(
                    template_name=str(template),
                    original_content=original_content,
                    new_content=content)

        if strict and unprocessed_vars:
            raise LookupError(f"you set option '--strict' and {msg}")
        logging.debug(msg)

        return content
    except Exception:
        raise


def print_diff(template_name: str, original_content: str, new_content: str):
    """print replaced lines"""
    DEFAULT = '\x1b[0m'
    GREEN = '\x1b[32m'
    RED = '\x1b[31m'

    for line in difflib.unified_diff(
            original_content.strip().splitlines(),
            new_content.strip().splitlines(),
            fromfile=template_name,
            tofile=template_name,
            lineterm='',
            n=0):
        for prefix in ('---', '+++', '@@'):
            if line.startswith(prefix):
                break
        else:
            if line.startswith('-'):
                msg = line.split('-', 1)[1:]
                color = RED
                diff = '-'
            elif line.startswith('+'):
                color = GREEN
                msg = line.split('+', 1)[1:]
                diff = '+'
            sys.stdout.write(f"{color}{diff}{DEFAULT}{msg[0]}\n")


def read_key_value_list(key_value_list: list,
                        delimiter: str = '=') -> dict:
    """extract key=value from string in a list of strings

    Arguments:
        key_value_list {list} -- list with strings (["key=value"]) to
                                 be splitted

    Keyword Arguments:
        delimiter {str} -- alternative delimiter (default: {'='})

    Raises:
        KeyError: same key passed more then one

    Returns:
        dict -- dictionary with extracted {key: value} pairs
    """
    key_value_dict = {}
    for key_value in key_value_list:
        if delimiter not in key_value:
            logging.warning(f"'{key_value}' has no valid delimiter "
                            f"({delimiter})")
            continue

        key, value = key_value.split(delimiter, 1)
        if not key:
            logging.warning(f"cannot get key from '{key_value}'")
            continue
        if not value:
            logging.warning(f"cannot get value from '{key_value}'")
            continue
        if key_value_dict.get(key):
            raise KeyError("you cannot pass the same key "
                           f"('{key}') multiple times with '-s|--set'")
        key_value_dict[key.strip()] = value.strip(' \n')

    return key_value_dict


def read_file(path: str,
              delimiter: str = '=') -> dict:
    """read .env or .json file and generate a dictionary with key: value

    Arguments:
        path {str} -- path to file with extra variables

    Keyword Arguments:
        delimiter {str} -- delimiter (default: {'='})

    Raises:
        FileNotFoundError: file to read does not exists
        TypeError: file suffix does not end with .env or .json

    Returns:
        dict -- dictionary with extracted key/value pairs
    """

    key_value_dict = {}

    if not os.path.isfile(path):
        raise FileNotFoundError(f"file '{path}' not found")

    extension = Path(path).suffix
    if extension == ".env":
        nr = 0
        with open(file=path, mode="r") as data:
            for line in data.readlines():
                nr += 1
                line = line.strip()
                try:
                    if not line.strip() or line.startswith("#"):
                        continue
                    if delimiter not in line:
                        raise SyntaxError(f"line {nr} in file '{path}' has no"
                                          f" valid delimiter ({delimiter})'")

                    key, value = line.split(delimiter, 1)
                    if not key:
                        raise KeyError(f"cannot get key from line {nr} "
                                       f"from file '{path}'")
                    if not value:
                        raise ValueError(f"cannot get value from line {nr}"
                                         f" from file '{path}'")

                    existing_value = key_value_dict.get(key)
                    if existing_value:
                        raise ReferenceError(f"key '{key}' in file '{path}' "
                                             f"(line {nr}) already set")

                    key_value_dict[key.strip()] = value.strip(' \'"\n')
                except Exception as e:
                    logging.warning(str(e).strip('"'))

    elif extension == ".json":
        with open(file=path, mode="r") as data:
            key_value_dict = json.load(data)
    else:
        raise TypeError(
                f"input file '{path}' does not end with '.env' or '.json'")
    return key_value_dict


def find_vars(text: str) -> list:
    """search in a text for '$' and '${}'

    Arguments:
        text {str} -- text to be searched

    Returns:
        list -- list with not replaced variables
    """
    return re.findall(pattern=pattern, string=text)


def main():
    try:
        args = parse_args()

        if not args.quiet:
            setup_logger(debug=args.debug)

        process(src=args.src,
                dst=args.dst,
                show_diff=args.diff,
                recursive=args.recursive,
                key_value_list=args.key_value_list,
                input_files=args.input_files,
                file_delimiter=args.delimiter,
                strict=args.strict,
                no_os_env=args.no_os_env,
                append=args.append,
                force=args.force,
                excludes=args.excludes)

    except KeyboardInterrupt:
        sys.stdout.flush()  # flush stream to prevent output mixup
        logging.warning(f"you manually abort\n")
        sys.exit(1)
    except Exception as e:
        sys.stdout.flush()  # flush stream to prevent output mixup
        logging.error(str(e).strip('"'))
        sys.exit(1)


if __name__ == "__main__":
    main()
