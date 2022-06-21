import glob
import importlib
import json
import os.path as osp
import re
import sys
from copy import deepcopy
from functools import partial
from typing import Any, Dict

_CFGOPT_PROTOCOL = "cfg://"
_NPRO = len(_CFGOPT_PROTOCOL)
_SEP_TOKEN = "/"

class CfgOptParseError(Exception): ...

class CfgOptParseResult:
    """This class stores a internal dict, and support 
    cfg:// format `__getitem__` and `__setitem__` method."""

    def __init__(self, data: Dict) -> None:
        self.data = data
        """stores the raw dict data."""
    
    def __getitem__(self, uri:str):
        keys = self._split_uri(uri)
        item = self.data
        try:
            for key in keys:
                item = self._get_item_from_list_or_dict(item, key)
            key_error = None
        except KeyError as e:
            key_error = str(e)
        finally:
            if key_error is not None:
                raise CfgOptParseError(f"While parsing {uri}, Key {key_error} does not exist.")

        if isinstance(item, (dict, list)):
            return CfgOptParseResult(item)
        else:
            return item
    
    def __setitem__(self, uri:str, data:Any):
        keys = self._split_uri(uri)
        item = self.data
        for key in keys[:-1]:
            item = self._get_item_from_list_or_dict(item, key)
        key = keys[-1]
        item[key] = data
    
    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({repr(self.data)})"
    
    @staticmethod
    def _get_item_from_list_or_dict(item, key):
        if isinstance(item, list):
            return item[int(key)]
        elif isinstance(item, dict):
            if key not in item:
                item[key] = {}
            return item[key]
        else:
            raise TypeError(f"Expect a list or dict, got {type(item)}.")
    
    def _split_uri(self, uri):
        # integer is for indexing lists
        if isinstance(uri, int):
            return [uri]
        # remove optional 'cfg://' prefix
        if uri.startswith(_CFGOPT_PROTOCOL):
            uri = uri[_NPRO:]
        # eliminate ".." in dict hiearchy keys
        def eliminate_parent(_keys):
            out = []
            for k in _keys:
                if k == "..":
                    out.pop()
                else:
                    out.append(k)
            return out
        # seperators "/" before first occurance of ".json"
        # are parsed as path sperator; after as dict hierarchy sperator.
        uri_find_json = uri.find(".json")
        if uri_find_json != -1:
            addr_sep = uri_find_json + 5
            keys = [uri[:addr_sep]]
            if addr_sep == len(uri) or addr_sep == len(uri) - 1:
                return keys
            keys.extend(eliminate_parent(uri[addr_sep+1:].split(_SEP_TOKEN)))
        else:
            keys = eliminate_parent(uri.split(_SEP_TOKEN))
        
        return keys
    
    def __getattr__(self, attrname):
        return getattr(self.data, attrname)
    
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self["__class__"](*args, **kwds)


def parse_configs(cfg_root:str) -> CfgOptParseResult:
    """This function load all json config files in `cfg_root`,
    updates it with command line options, follows and substitute
    the `cfg://` block references."""

    # load raw data from json files
    root = {}
    cfg_file_glob_pattern = osp.join(cfg_root, "**", "*.json")
    for cfg_file in glob.glob(cfg_file_glob_pattern, recursive=True):
        cfg_addr = osp.relpath(cfg_file, cfg_root)
        with open(cfg_file) as _f:
            try:
                cfg_data = json.load(_f)
                json_error = None
            except json.JSONDecodeError as e:
                json_error = str(e)
            finally:
                if json_error:
                    raise CfgOptParseError(f"While parsing {cfg_file}, {json_error}.")
        root[cfg_addr] = cfg_data

    router = CfgOptParseResult(root)

    # use command line options to update json configs
    updator_pattern = re.compile("^--(.*\.json.*)=(.*)")
    for updator in sys.argv:
        match_obj = updator_pattern.fullmatch(updator)
        if match_obj:
            uri, data = match_obj.group(1, 2)
            try:
                data = json.loads(data)
                json_error = None
            except json.JSONDecodeError as e:
                json_error = str(e)
            finally:
                if json_error:
                    raise CfgOptParseError(f"While parsing {data}, {json_error}.")
            router[uri] = data

    # parse block reference
    def parse_json_block_reference(data, uri):
        if isinstance(data, dict):
            for k in data:
                data[k] = parse_json_block_reference(data[k], f"{uri}/{k}")
        elif isinstance(data, list):
            data = [parse_json_block_reference(d, f"{uri}/{i}") for i, d in enumerate(data)]
        elif isinstance(data, str) and data.startswith(_CFGOPT_PROTOCOL):
            if ".json" not in data:  # will be interpret as a relative uri
                data = f"{uri}/{data}"
            data = router[data]
            if isinstance(data, CfgOptParseResult):
                data = data.data
        return data
    
    parse_json_block_reference(root, _CFGOPT_PROTOCOL)

    # parse inheritance (2 tasks)
    
    ## (1/2) inherit from __base__;
    def parse_inheritance(data):
        if isinstance(data, dict):
            if "__base__" in data:
                base:Dict = deepcopy(parse_inheritance(data["__base__"]))
                data.pop("__base__")
                base.update(data)
                data.update(base)
            for k in data:
                data[k] = parse_inheritance(data[k])
        elif isinstance(data, list):
            data = [parse_inheritance(_) for _ in data]
        return data
    
    parse_inheritance(root)

    ## (2/2) use nested uri key to update json configs;
    def update_with_nested_uri_key(data):
        if isinstance(data, dict):
            for k in data:
                if k.startswith("__"): continue
                if "/" not in k: continue
                CfgOptParseResult(data)[k] = update_with_nested_uri_key(data.pop(k))
        elif isinstance(data, list):
            data = [parse_python_objects(_) for _ in data]
        return data
    
    update_with_nested_uri_key(root)

    # parse python objects
    def parse_python_objects(data):
        if isinstance(data, dict):
            for k in data:
                if k.startswith("__"): continue
                data[k] = parse_python_objects(data[k])
            if "__module__" in data and "__class__" in data and isinstance(data["__class__"], str):
                module = importlib.import_module(data["__module__"])
                klass = getattr(module, data["__class__"])
                data["__class__"] = partial(klass, **{k:v for k, v in data.items() if not k.startswith("__")})
        elif isinstance(data, list):
            data = [parse_python_objects(_) for _ in data]
        return data
    
    parse_python_objects(root)

    return router
