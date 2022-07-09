import glob
import importlib
import json
import os.path as osp
import re
import types
import jsbeautifier
import sys
from copy import deepcopy
from inspect import Parameter, signature, isclass, isfunction
from typing import Any, Dict, Union
from socket import gethostname
from collections import abc

_AST = "__as_type__"
_BSE = "__base__"
_CLS = "__class__"
_HST = "__hostname__"
_MOD = "__module__"
_PRT = ".."  # parent
_PTC = "cfg://"  # protocal
_PTL = len(_PTC)  # protocal length
_SEP = "/"  # seperator

undefined = f"{_PTC}__undefined__"

def _remove_protocol_prefix(uri):
    if uri.startswith(_PTC):
        uri = uri[_PTL:]
    return uri

class ConfigParseError(Exception): ...

class URINotFoundError(Exception): ...

def _get_parameters(klass):
    if isclass(klass):
        parameters = list(signature(klass.__init__).parameters.items())[1:]
    elif isfunction(klass):
        parameters = list(signature(klass).parameters.items())
    elif hasattr(klass, "__call__"):
        parameters = list(signature(klass.__call__).parameters.items())
    else:
        raise ConfigParseError(f"Unknown Python Callable {klass.__name__}")
    return parameters

def wrap(data):
    return ConfigContainer(data) if isinstance(data, dict) else data

def dewrap(data):
    if isinstance(data, ConfigContainer):
        return data.data
    elif isinstance(data, dict):
        return {k:dewrap(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [dewrap(v) for v in data]
    else:
        return data
    
class ConfigContainer:
    """This class stores a internal dict, and support 
    cfg:// format `__getitem__` and `__setitem__` method."""

    def __init__(self, data: Dict) -> None:
        self.data = data
        """stores the raw dict data."""
    
    def items(self):
        if not isinstance(self.data, abc.Mapping):
            raise TypeError()
        for k, v in self.data.items():
            yield k, wrap(v)
    
    def values(self):
        if not isinstance(self.data, abc.Mapping):
            raise TypeError()
        for v in self.data.values():
            yield wrap(v)
        
    def to_json(self, file=None):
        
        json_str = jsbeautifier.beautify(json.dumps(dewrap(self.data)))
        if file is not None:
            with open(file, 'w') as writer:
                writer.write(json_str)
        return json_str
    
    def __eq__(self, other):
        if isinstance(other, ConfigContainer):
            other = other.data
        return self.data == other
    
    def __getitem__(self, uri:str):
        keys = self._split_uri(uri)
        item = self.data
        try:
            for key in keys:
                item = self._get_item_from_list_or_dict(item, key)
        except:
            msg = f"While addressing '{uri}', key '{key}' does not exist"
            if isinstance(item, (dict, list)):
                msg += f", available keys are {[k for k in item]}"
                
            # error message will show the line calling "data[key]" from outer frame.
            traceback = sys.exc_info()[2]
            back_frame = traceback.tb_frame.f_back
            back_tb = types.TracebackType(tb_next=None,
                                  tb_frame=back_frame,
                                  tb_lasti=back_frame.f_lasti,
                                  tb_lineno=back_frame.f_lineno)
            raise URINotFoundError(msg).with_traceback(back_tb) from None

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
        self._set_item_from_list_or_dict(item, key, data)
    
    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({repr(self.data)})"
    
    @staticmethod
    def _get_item_from_list_or_dict(item, key):
        """ Robust version of `item[key]`, that also applies to list (not only dict)."""
        if key == "":
            return KeyError("Empty keys are not allowed.")
        elif isinstance(item, list):
            return item[int(key)]
        elif isinstance(item, (dict, ConfigContainer)):
            return item[key]
        elif item is None:
            raise KeyError(key)
        else:
            raise TypeError(f"Expect a list or dict, got {type(item)}.")

    @staticmethod
    def _set_item_from_list_or_dict(item, key, value):
        """ Robust version of `item[key] = value`, that also applies to list (not only dict)."""
        if key == "":
            return KeyError("Empty keys are not allowed.")
        elif isinstance(item, list):
            item[int(key)] = value
        elif isinstance(item, (dict, ConfigContainer)):
            item[key] = value
        else:
            raise TypeError(f"Expect a list or dict, got {type(item)}.")
    
    def _split_uri(self, uri):
        # integer is for indexing lists
        if isinstance(uri, int):
            return [uri]
        # remove optional 'cfg://' prefix
        uri = _remove_protocol_prefix(uri)
        # translate special keys in dict hiearchy keys
        def translate_uri(_keys):
            out = []
            for k in _keys:
                if k == _PRT:
                    out.pop()
                elif k == _HST:
                    out.append(gethostname())
                elif k == "":
                    continue
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
            keys.extend(translate_uri(uri[addr_sep+1:].split(_SEP)))
        else:
            keys = translate_uri(uri.split(_SEP))
        
        return keys
    
    def __getstate__(self):
        return self.data

    def __setstate__(self, data):
        self.data = data
    
    def __getattr__(self, attrname):
        return getattr(self.data, attrname)
    
    def __call__(self, *args: Any, recursive=True, **kwds: Any) -> Any:
        
        def instantiate(data, *_args, **_kwds):
            if _MOD in data and _CLS in data:
                module = importlib.import_module(data[_MOD])
                klass = getattr(module, data[_CLS])
                # update args
                try:
                    for (k, p), arg in zip(_get_parameters(klass), _args):
                        if p.kind == Parameter.POSITIONAL_OR_KEYWORD:
                            data[k] = arg
                        else:
                            raise ConfigParseError(f'Can\'t parse argument \'{k}\' for {data[_CLS]}.')
                except ValueError as e:
                    if "no signature found" in e.args[0]:
                        if len(_args):
                            raise ConfigParseError(f"Please use keyword to pass in arguments for `{data[_CLS]}`.") from e
                # update kwds
                for k, p in _get_parameters(klass):
                    if p.kind == Parameter.VAR_KEYWORD and p.name in data:
                        var_keyword_subdict = data.pop(p.name)
                        data.update(var_keyword_subdict)
                data.update(deepcopy(_kwds))
                
                # check wether klass accept variable keyword
                if Parameter.VAR_KEYWORD not in [p.kind for _, p in _get_parameters(klass)]:
                    accept_args = [k for k, p in _get_parameters(klass)]
                    for k in data:
                        if k.startswith("__"):
                            continue
                        if k not in accept_args:
                            raise ConfigParseError(f"Unsupported parameter '{k}' for class '{klass.__name__}'.")
                        
                for k, p in _get_parameters(klass):
                    if p.kind == Parameter.POSITIONAL_ONLY:
                        raise ConfigParseError(f"Unsupported parameter type '{p.kind}' for class '{klass.__name__}'.")
                
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
            data = deepcopy(self.data)

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


def parse_configs(cfg_root:Union[str, Dict], args=None, args_root=None) -> ConfigContainer:
    """This function load all json config files in `cfg_root`,
    updates it with command line options, follows and substitute
    the `cfg://` block references."""

    if isinstance(cfg_root, str):
        if not osp.isdir(cfg_root):
            raise TypeError(f"`cfg_root` (\"{cfg_root}\") is not a directory.")
        # load raw data from json files
        root = {}
        cfg_file_glob_pattern = osp.join(cfg_root, "**", "*.json")
        for cfg_file in glob.glob(cfg_file_glob_pattern, recursive=True):
            cfg_addr = osp.relpath(cfg_file, cfg_root)
            with open(cfg_file) as _f:
                try:
                    cfg_data = json.load(_f)
                except json.JSONDecodeError as e:
                    raise ConfigParseError(f"While parsing {cfg_file}, {e}.") from None
            root[cfg_addr] = cfg_data
    elif isinstance(cfg_root, dict):
        root = cfg_root
    else:
        raise TypeError(f"Type of `cfg_root` not supported, expect directory string or a dict, got `{type(cfg_root)}`.")

    router = ConfigContainer(root)

    # use command line options to update json configs
    def command_line_update(_args):
        updator_pattern = re.compile("^--(.*?)=(.*)")
        unparsed_args = []
        for updator in _args:
            match_obj = updator_pattern.fullmatch(updator.replace("\n", ""))
            if match_obj:
                uri_, data = match_obj.group(1, 2)
                if args_root is None:
                    uri = uri_
                else:
                    uri = _SEP.join([args_root, uri_])
                # delay update if uri not exists:
                try:
                    router[uri]
                except URINotFoundError as e:
                    unparsed_args.append(updator)
                    continue
                # try parse data
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    raise ConfigParseError(f"While parsing {data}, {e}.") from None
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
        elif isinstance(data, str) and data.startswith(_PTC) and data != undefined:
            backup_data = data
            try:
                if ".json" not in data:  # will be interpret as a relative uri
                    data = f"{uri[:uri.rfind(_SEP)]}/{_remove_protocol_prefix(data)}"
                data = router[data]
                if isinstance(data, ConfigContainer):
                    data = data.data
            except Exception as e:
                if not failok:
                    raise type(e)(f"{e.args[0]}\nConfig origin: {uri}") from None
                data = backup_data
        return data
    
    # first time parsing might fail because inheritance is not parsed yet.
    parse_json_block_reference(root, _PTC[:-1], failok=True)

    # parse inheritance
    def parse_inheritance(data, uri):
        if isinstance(data, dict):
            if _BSE in data:
                base:Dict = deepcopy(parse_inheritance(data[_BSE], f"{uri}/{_BSE}"))
                if not isinstance(base, abc.Mapping):
                    breakpoint()
                    raise ConfigParseError(f"Unable to inherit the base object since it is not parsed as a dict. The base object is: {repr(base)}\nConfig origin: '{uri}/{_BSE}'")
                data.pop(_BSE)
                base.update(data)
                data.update(base)
            for k in list(data.keys()):
                if "/" in k:
                    try:
                        ConfigContainer(data)[k] = parse_inheritance(data.pop(k), f"{uri}/{k}")
                    except KeyError as e:
                        msg = f"While addressing '{e.args[0]}', inheritance key '{k}' does not exist.\nConfig origin: {uri}"
                        raise URINotFoundError(msg) from None
                else:
                    data[k] = parse_inheritance(data[k], f"{uri}/{k}")
        elif isinstance(data, list):
            data = [parse_inheritance(_, f"{uri}/{i}") for i, _ in enumerate(data)]
        return data
    
    parse_inheritance(root, _PTC[:-1])
    
    # parse_json_block_reference again
    try:
        parse_json_block_reference(root, _PTC[:-1], failok=False)
    except Exception as e:
        raise type(e)(*e.args) from None

    # parse python objects
    def parse_python_objects(data, uri):
        if isinstance(data, dict):
            for k in data:
                if k.startswith("__"): continue
                data[k] = parse_python_objects(data[k], f'{uri}/{k}')
            if _MOD in data and _CLS in data:
                try:
                    module = importlib.import_module(data[_MOD])
                except ModuleNotFoundError as e:
                    raise ConfigParseError(f"Trying to import '{data[_MOD]}', but n{str(e.args[0])[1:]}. Check your PYTHONPATH.\nConfig origin: '{uri}'")
                try:
                    klass = getattr(module, data[_CLS])
                except AttributeError as e:
                    raise ConfigParseError(f"{str(e.args[0])}\nConfig origin: '{uri}'")

                # fill omitted params with defaults
                try:
                    for k, param in _get_parameters(klass):
                        if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
                            if k in data:
                                continue
                            elif param.default is Parameter.empty:
                                data[k] = undefined
                            else:
                                pass
                except ValueError as e:
                    if "no signature found" in e.args[0]: pass
        elif isinstance(data, list):
            data = [parse_python_objects(_, f'{uri}/{i}') for i, _ in enumerate(data)]
        return data

    try:
        parse_python_objects(root, _PTC[:-1])
    except ConfigParseError as e:
        raise ConfigParseError(str(e)) from None

    # command line update again (this time including expanded and inherited fields.)
    unparsed_args = command_line_update(unparsed_args)
    
    if len(unparsed_args):
        unparsed_args_ = ', '.join(f"'{ua[:ua.find('=')+1]}...'" for ua in unparsed_args)
        
        raise ConfigParseError(
            f"Some command args are not found in the config definition thus failed to be updated. They are [{unparsed_args_}]. Please double check the URI path.")
    
    return router
