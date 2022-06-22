import glob
import importlib
import json
import os.path as osp
import re
import sys
from copy import deepcopy
from inspect import Parameter, signature, isclass, isfunction
from typing import Any, Dict, Union

_PTC = "cfg://"
_NPR = len(_PTC)
_SEP = "/"
_MOD = "__module__"
_CLS = "__class__"
_BSE = "__base__"
_AST = "__as_type__"

undefined = f"{_PTC}__undefined__"

def _remove_protocol_prefix(uri):
    if uri.startswith(_PTC):
        uri = uri[_NPR:]
    return uri

class CfgOptParseError(Exception): ...

def _get_parameters(klass):
    if isclass(klass):
        parameters = list(signature(klass.__init__).parameters.items())[1:]
    else:
        parameters = list(signature(klass).parameters.items())
    return parameters

class ConfigContainer:
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
        except:
            msg = f"While parsing '{uri}', key '{key}' does not exist"
            if isinstance(item, (dict, list)):
                msg += f", available keys are '{[k for k in item]}'"
            raise CfgOptParseError(msg) from None

        if isinstance(item, (dict, list)):
            return ConfigContainer(item)
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
            return item[key]
        else:
            raise TypeError(f"Expect a list or dict, got {type(item)}.")
    
    def _split_uri(self, uri):
        # integer is for indexing lists
        if isinstance(uri, int):
            return [uri]
        # remove optional 'cfg://' prefix
        uri = _remove_protocol_prefix(uri)
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
            keys.extend(eliminate_parent(uri[addr_sep+1:].split(_SEP)))
        else:
            keys = eliminate_parent(uri.split(_SEP))
        
        return keys
    
    def __getstate__(self):
        return self.data

    def __setstate__(self, data):
        self.data = data
    
    def __getattr__(self, attrname):
        return getattr(self.data, attrname)
    
    def __call__(self, *args: Any, recursive=True, **kwds: Any) -> Any:
        
        def wrap(data): return ConfigContainer(data) if isinstance(data, dict) else data

        def instantiate(data, *_args, **_kwds):
            if _MOD in data and _CLS in data:
                module = importlib.import_module(data[_MOD])
                klass = getattr(module, data[_CLS])
                parameters = _get_parameters(klass)
                # update args and kwds
                for (k, p), arg in zip(parameters, _args):
                    if p.kind == Parameter.POSITIONAL_OR_KEYWORD:
                        data[k] = deepcopy(arg)
                    else:
                        raise CfgOptParseError(f'Can\'t parse arguments for {data[_CLS]}.')
                data.update(deepcopy(_kwds))
                # if there is any required param yet undefined, do not instantiate
                for v in data.values():
                    if v == undefined: return data
                else: # else instantiate
                    return klass(**{k:wrap(v) for k, v in data.items() if not k.startswith("__")})
            else: # fallback to direct call
                return data(*_args, **_kwds)
            
        if recursive:
            def recursive_instantiate(data, root):
                if isinstance(data, dict):
                    for k in data:
                        if k.startswith("__"): continue
                        data[k] = recursive_instantiate(data[k], False)
                    if not root and _CLS in data and not data.get(_AST, False):
                        data = instantiate(data)
                elif isinstance(data, list):
                    data = [recursive_instantiate(d, False) for d in data]
                return data
            data = recursive_instantiate(deepcopy(self.data), root=True)
        else:
            data = self.data

        return instantiate(data, *args, **kwds)
    
    def __contains__(self, uri):
        try:
            self[uri]
            return True
        except:
            return False


def PartialClass(klass, *args, **kwds):

    cfg_dict = {
        _MOD: klass.__module__,
        _CLS: klass.__qualname__
    }

    # set defaults
    for k, param in signature(klass).parameters.items():
        if param.default is Parameter.empty:
            cfg_dict[k] = undefined
        else:
            cfg_dict[k] = param.default

    # update args
    for k, arg in zip(signature(klass).parameters.keys(), args):
        cfg_dict[k] = deepcopy(arg)

    # update kwds
    cfg_dict.update(deepcopy(kwds))

    return ConfigContainer(cfg_dict)


def parse_configs(cfg_root:Union[str, Dict], args=None) -> ConfigContainer:
    """This function load all json config files in `cfg_root`,
    updates it with command line options, follows and substitute
    the `cfg://` block references."""

    if isinstance(cfg_root, str) and osp.isdir(cfg_root):
        # load raw data from json files
        root = {}
        cfg_file_glob_pattern = osp.join(cfg_root, "**", "*.json")
        for cfg_file in glob.glob(cfg_file_glob_pattern, recursive=True):
            cfg_addr = osp.relpath(cfg_file, cfg_root)
            with open(cfg_file) as _f:
                try:
                    cfg_data = json.load(_f)
                except json.JSONDecodeError as e:
                    raise CfgOptParseError(f"While parsing {cfg_file}, {e}.") from None
            root[cfg_addr] = cfg_data
    elif isinstance(cfg_root, dict):
        root = cfg_root
    else:
        raise TypeError(f"Type of `cfg_root` not supported, expect directory string or a dict, got `{type(cfg_root)}`.")

    router = ConfigContainer(root)

    # use command line options to update json configs
    def command_line_update(_args):
        updator_pattern = re.compile("^--(.*)=(.*)")
        unparsed_args = []
        for updator in _args:
            match_obj = updator_pattern.fullmatch(updator)
            if match_obj:
                uri, data = match_obj.group(1, 2)
                # delay update if uri not exists:
                try:
                    router[uri]
                except CfgOptParseError:
                    unparsed_args.append(updator)
                    continue
                # try parse data
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    raise CfgOptParseError(f"While parsing {data}, {e}.") from None
                router[uri] = data  # this line updates root
        return unparsed_args
        
    args = deepcopy(args if args is not None else sys.argv[1:])
    unparsed_args = command_line_update(args)

    # parse block reference
    def parse_json_block_reference(data, uri, failok=False):
        if isinstance(data, dict):
            for k in data:
                data[k] = parse_json_block_reference(data[k], f"{uri}/{k}", failok)
        elif isinstance(data, list):
            data = [parse_json_block_reference(d, f"{uri}/{i}", failok) for i, d in enumerate(data)]
        elif isinstance(data, str) and data.startswith(_PTC):
            backup_data = data
            try:
                if ".json" not in data:  # will be interpret as a relative uri
                    data = f"{uri[:uri.rfind(_SEP)]}/{_remove_protocol_prefix(data)}"
                data = router[data]
                if isinstance(data, ConfigContainer):
                    data = data.data
            except:
                if not failok: raise
                data = backup_data
        return data
    
    # first time parsing might fail because inheritance is not parsed yet.
    parse_json_block_reference(root, _PTC[:-1], failok=True)

    # parse inheritance (2 tasks)
    
    ## (1/2) inherit from __base__;
    def parse_inheritance(data):
        if isinstance(data, dict):
            if _BSE in data:
                base:Dict = deepcopy(parse_inheritance(data[_BSE]))
                data.pop(_BSE)
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
            for k in list(data.keys()):
                if k.startswith("__"): continue
                if "/" in k:
                    ConfigContainer(data)[k] = update_with_nested_uri_key(data.pop(k))
                else:
                    data[k] = update_with_nested_uri_key(data[k])
        elif isinstance(data, list):
            data = [update_with_nested_uri_key(_) for _ in data]
        return data
    
    update_with_nested_uri_key(root)

    # parse_json_block_reference again
    try:
        parse_json_block_reference(root, _PTC[:-1], failok=False)
    except CfgOptParseError as e:
        raise CfgOptParseError(str(e)) from None

    # parse python objects
    def parse_python_objects(data):
        if isinstance(data, dict):
            for k in data:
                if k.startswith("__"): continue
                data[k] = parse_python_objects(data[k])
            if _MOD in data and _CLS in data:
                module = importlib.import_module(data[_MOD])
                klass = getattr(module, data[_CLS])

                # fill omitted params with defaults
                for k, param in _get_parameters(klass):
                    if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
                        if k in data:
                            continue
                        elif param.default is Parameter.empty:
                            data[k] = undefined
                        else:
                            data[k] = param.default
        elif isinstance(data, list):
            data = [parse_python_objects(_) for _ in data]
        return data

    parse_python_objects(root)

    # command line update again (this time including expanded and inherited fields.)
    unparsed_args = command_line_update(unparsed_args)

    return router
