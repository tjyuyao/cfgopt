
<p align="center"><img src="https://github.com/tjyuyao/cfgopt/raw/main/cfgopt.png" alt="Logo"></p>

## Introduction

`cfgopt` is a solution for elegance of configuring complicated deep learning projects. Here, you configure everything only once in json, without need to write configuration and commandline parsing boilerplate code in python anymore. The solution is extremly simple, elegant, and compact. Without any 3rd-party dependency, the core implementation of `cfgopt` is only around 200 LOC, and *will be* (todo) fully tested.

## News

- **2022/06/21** `cfgopt` code released.

## Getting Started

**Installation**

```
pip install cfgopt
```

**Basic Usage**

Generally, you should have some json **c**on**f**i**g** files in a folder, and a python program that import `cfgopt` to parse them. The program can have command line **opt**ions that update specific field in the parsed results for this running. This is also why this library is called "cfgopt".

To be concrete, you have two choices using `cfgopt`:

- Use the `cfgopt.parse_configs(cfg_root)` API, just pass in the directory path of all the configuration files, and explore with the results! Or you should read the examples described in the [Features](https://github.com/tjyuyao/cfgopt#features) section.
- Use `cfgoptrun` command directly or wrap `cfgopt.main()` function, for details please refer to the follow-up [main function](https://github.com/tjyuyao/cfgopt#main-function) section.

## Features

<details><summary><h3>basic json binding</h3></summary><p>

`cfgopt` has a main api `parse_configs(cfg_root)` that accepts the path of *a folder of json files*. All files will be (recursively) load in python and added to a root `dict`, keeping the hierarchy and data types unchanged, with some exceptions described in follow-up sections.

> Feature first added in `v0.1`.

</p></details>

<details><summary><h3>block-level reference</h3></summary><p>

`cfgopt` release you from repeating yourself with a mountain pile of configuration files by borrowing the concept of `block-level reference and embedding` in many modern note-taking apps such as `Logseq`, or more well-known `hyperlinks` for webpages.

**The `cfg://` format URI:**

`cfgopt` follows and expands string values matching a special syntax `cfg://<file-path>/<intra-file-uri>` in the configuration files during parsing. This is one of the most repealing feature for `cfgopt`. You can also specify *relative* uri which contains no substring ".json" in it.

**Example:**

**file structure**

```shell
.
└── test_blockref_in_list
    ├── cfg
    │   ├── data.json
    │   └── recipes.json
    └── test_blockref_in_list.py
```

**data.json**:

```json
{
    "data1": {
        "meta": {
            "location": "/data/1/loc"
        }
    },
    "data2": {
        "meta": {
            "location": "/data/2/loc"
        }
    }
}
```

**recipes.json**:

```json
{
    "recipe1": {
        "use_data": [
            "cfg://data.json/data1"
        ]
    },
    "recipe2": {
        "use_data": [
            "cfg://data.json/data1",
            "cfg://data.json/data2"
        ]
    }
}
```

**test_blockref_in_list.py**
```python
import cfgopt

def test_blockref_in_list():
    cfg = cfgopt.parse_configs(cfg_root='test_blockref_in_list/cfg')

    # following lines are equivalent
    assert cfg["recipes.json"]["recipe2"]["use_data"][1]["meta"]["location"] == "/data/2/loc"
    assert cfg["recipes.json"]["recipe2/use_data/1/meta/location"] == "/data/2/loc"
    assert cfg["recipes.json/recipe2/use_data/1/meta/location"] == "/data/2/loc"
```

> Relative URI support added in `v0.3.0`.
> Feature first added in `v0.1`.

</p></details>

<details><summary><h3>command-line update</h3></summary><p>

`cfgopt` will automatically parse command line options matching the python regex format `^--(.*\.json.*)=(.*)`, and interpret it as an update of the parsed configuration folder. The right hand side of `=` should be valid json, and you might need to take care of shell escaping your special characters.

For example, you can write `--train.json/max_epochs=100` or `--train.json/max_epochs="100"`, since your shell would escape double-quotes, you will get an integer `100` in both cases.

But if you write `--train.json/resume=\"/path/to/ckpt\"` or `--train.json/resume='"/path/to/ckpt"'`, you should probably get a string value, which depends on your shell implementation.

> Updated regex format from `^--(.*)=(.*)` to `^--(.*\.json.*)=(.*)` in `v0.2`.
> Feature first added in `v0.1`.

</p></details>

<details><summary><h3>json objects inheritance</h3></summary><p>

Users can specify a json dict, that contains a `__base__` field, linking to another base json dict objects with the `cfg://` reference format (described in [block-level reference](https://github.com/tjyuyao/cfgopt#block-level-reference)). Then the current dict would inherit the base object, and also has its own values in normal fields. This feature is also critical to eliminate repeating, with which now you can develop multiple simillar configs from some prototypes.

> TODO: an example.

> Bugfix: changed from referencing to deepcopying the base dict in `v0.2`.

> Feature first added in `v0.1`.

</p></details>

<details><summary><h3>parse python objects</h3></summary><p>

`cfgopt` has a extremly flexible feature, that parse an json dict to almost ANY python objects defined in user's code or any code python can find in `PYTHON_PATH`.

Users can specify a json dict, that contains `__module__` and `__class__` field. The `__module__` field will be imported by `importlib.import_module()` during parsing, and `__class__` field naming any python `callable` in the imported module will be passed to `functools.partial()` along with other fields as keyword arguments. Finally, the mapped "dict" in python would be directly callable to instantiate corresponding class or get result of corresponding functions.

**pseudo-code of parsing:**
```python
if "__module__" in data and "__class__" in data and isinstance(data["__class__"], str):
    module = importlib.import_module(data["__module__"])
    klass = getattr(module, data["__class__"])
    data["__class__"] = partial(klass, **{k:v for k, v in data.items() if not k.startswith("__")})
```

> TODO: an example.

> API enhance: user now can directly call the mapped "dict" object instead of its `__class__` field in `v0.2`.

> Feature first added in `v0.1`.

</p></details>

<details><summary><h3>main function</h3></summary><p>

```python
import argparse
import cfgopt

def main(*args, **kwds):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "recipe",
        help="a main function uri to be execute."
    )
    parser.add_argument(
        "-d", "--cfgdir",
        default="cfg",
        help="config directory that maps to cfg:// root."
    )
    args, _ = parser.parse_known_args()
    cfgs = cfgopt.parse_configs(cfg_root=args.cfgdir)
    return cfgs[args.recipe](*args, **kwds)


if __name__ == "__main__":
    main()
```

This example `main()` function accepts the first argument as a previous described `cfg://`-format uri, that parses a python callable function, and call it as the main function. This is also implemented as `cfgopt.main()`, and user can use `cfgoptrun` command direct from shell, or just import this main function and call it in usercode with extra python arguments.

> TODO: an example.

> Add `cfgoptrun` command (entrypoint) in `v0.2`.

> Feature first added in `v0.1`.

</p></details>