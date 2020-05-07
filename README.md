# templator

Replace all instances of `$VAR` / `${VAR}` in a file with the corresponding values and send the result to stdout or to a file.

## Usage

```bash
usage: templator.py [--diff]
                    [-r|recursive]
                    [-e|--exclude [STRING [STRING] ...]]
                    [--debug] | [-q|--quiet]
                    [--strict]
                    [-s|--set [KEY=VALUE [KEY=VALUE ...]]]
                    [-i|--input [PATH [PATH ...]]] [-d|--delimiter-in-files DELIMITER]
                    [--no-os-env]
                    [-o|--output PATH] [-a|--append ] [-f|--force]
                    [-v|--version] | [-h|--help]
                    PATH [PATH ...]
```

## Arguments

Positional arguments:

| argument            | description           |
| ------------------- | --------------------- |
| `PATH` [`PATH` ...] | path to template file |

Optional arguments:

| arguments                                | description                                           |
| ---------------------------------------- | ----------------------------------------------------- |
| `--diff`                                 | show replaced lines                                   |
| `-e`, `--exclude` `STRING` [`STRING`...] | exclude path containing `STRING`                      |
| `-r`, `--recursive`                      | process templates directory recursively               |
| `--debug`                                | set log level to `debug`                              |
| `-q`, `--quiet`                          | do not output log                                     |
| `--strict`                               | raise an error if not all variables could be replaced |
| `-v`, `--version`                        | show version number and exit                          |
| `-h`, `--help`                           | show this help message and exit                       |

Setting variables:

| arguments                                   | description                                                |
| ------------------------------------------- | ---------------------------------------------------------- |
| `-s`, `--set` `KEY=VALUE` [`KEY=VALUE` ...] | pass key=value pair as variable                            |
| `-i`, `--input` `PATH` [`PATH` ...]         | files containing variable(s)                               |
| `-d`, `--delimiter-in-file` `DELIMITER`     | set delimiter for key/value pairs in __files__. default: = |
| `--no-os-env`                               | do not use os environment                                  |

Redirect output:

| arguments               | description                            |
| ----------------------- | -------------------------------------- |
| `-o`, `--output` [PATH] | redirect output to file or a directory |
| `-a`, `--append`        | append to output file PATH             |
| `-f`, `--force`         | replace existing output file           |

## Supported variable types

Supports $-based substitutions, using the following rules:

* `$$` is an escape; it is replaced with a single `$`.
* `$identifier` names a substitution placeholder matching a mapping key of "identifier". By default, "identifier" is restricted to any case-insensitive ASCII alphanumeric string (including underscores) that starts with an underscore or ASCII letter. The first non-identifier character after the `$` character terminates this placeholder specification.
* `${identifier}` is equivalent to `$identifier`. It is required when valid identifier characters follow the placeholder but are not part of the placeholder, such as "`${noun}`ification".

## Passing variables

Variables can be passed as followed:

* directly with `key=value` pairs (parameter `-s KEY=VALUE [KEY=VALUE ...]`)
* from .json and/or .env files (parameter `-i PATH [PATH ...]`)
* from os environment variables (can be disabled with parameter `--no-os-env`)

If a variable could not be replaced, it will be leave as it is!
To show te unreplaced variables add the parameter `--strict`.

## Replacement order

The order of replacing variables is:

* directly passed key=value pairs (`-s`) \*
* input files (`-i`) \*
* os environment variables

*\*in order you pass them to the script*

## Directly with `key=value` pairs

Pass directly (multiple) variables as key=value pair:

```bash
formater.py template.yaml -s user=admin password='this is my special pa$$word!'
```

**Note**  
Use single quotes for not escaping characters!

## Input files

You can pass (multiple) files containing variables.  
Input files must have the suffix `.json` or `.env`.

### Examples

credentials.env:

```bash
user=admin
password = this is my special pa$$word!
```

**Note**  
If you have the same key multiple time in the same file, it use the __last occurrence__!  
You can change the delimiter for `*.env`-files with the parameter `-d|--delimiter-in-file`

You can __NOT__ also add nested `*.json`-files:

credentials.json:

```json
{
    'user': 'admin',
    'password': 'this is my special pa$$word!'
}
```

**Note**  
The [rfc 4627](http://tools.ietf.org/html/rfc4627#section-2.2) for application/json media type recommends unique keys but it doesn't forbid them explicitly.  

The `value` of the __last occurrence__ of the same `key` will be used!

## OS environment variables

By default the script try to replace variables with os environment variables.  
Use `export key=value` to use variables directly from the shell. Without `export` the script can not access os environment variables!

```bash
export user="admin"
export password='this is my special pa$$w0rd!'
```

**Note**  
use single quotes for not escaping characters!

## Output to a file

You can redirect the output to a file or a directory.  
If the output is a directory, it will keep the template filename and the direcotry structure.  
If the file exists, you can pass the parameter `-a|--append` to append the output or `-f|--force` to replace the content.

### Examples

Redirect output of one template to one file:

```bash
python3 /opt/templator/templator.py /home/user/templates/nginx.yaml -o /home/user/files/nginx.yaml
```

Redirect output of two templates to one file:

```bash
python3 /opt/templator/templator.py /home/user/templates/nginx.yaml /home/user/templates/nginx_additional.yaml -o /home/user/files/nginx.yaml --append
```

Process each file in current directory and redirect the output for each template to a separate file:

```bash
python3 /opt/templator/templator.py templates -o ~/files/templates/
```

**Note**  

Without trailing slash on the template directory it will create the template directory in the output directory:  
`templates` => `~/files/templates/`  
With trailing slash it will put the processed files directly in the output directory:  
`templates/` => `files/`

## Exclude

Skip path containing a `STRING`.

### Examples

Do not process `*.md` files:

```bash
python3 /opt/templator/templator.py templates/ -o ~/files/templates/ -e "*.md"
```

Do not process folders containing `static`:

```bash
python3 /opt/templator/templator.py templates/ -o ~/files/templates/ -e "static"
```
