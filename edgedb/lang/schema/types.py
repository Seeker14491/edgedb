##
# Copyright (c) 2012=2016 MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import itertools
import types

from metamagic.utils import ast
from metamagic.utils import functional

from . import error as s_err
from . import objects as so
from . import pointers as s_pointers


class TypeRules:
    rules = {}

    @classmethod
    def add_rule(cls, op, args, result):
        cls.rules.setdefault(op, {}).setdefault(len(args), {})[tuple(args)] = result

    @classmethod
    def get_result(cls, op, args, schema):
        match = None
        rules = cls.rules.get(op)

        if rules:
            rules = rules.get(len(args))

        if rules:
            for sig, result in rules.items():
                for i, arg in enumerate(args):
                    sig_arg = sig[i]
                    if not (isinstance(arg, type) and issubclass(arg, sig_arg)) and \
                            not (isinstance(arg, so.ProtoObject) and arg.issubclass(sig_arg)):
                        break
                else:
                    match = result
                    break

        if match and match.__class__ is str:
            match = schema.get(match)

        return match


class TypeInfoMeta(type):
    def __new__(mcls, name, bases, dct, *, type):
        result = super().__new__(mcls, name, bases, dct)

        if type is not None:
            for name, proc in dct.items():
                if not isinstance(proc, types.FunctionType):
                    continue

                astop = ast.ops.Operator.funcname_to_op(name)

                if astop:
                    args = functional.get_argsspec(proc)

                    argtypes = []
                    for i, arg in enumerate(itertools.chain(args.args, args.kwonlyargs)):
                        if i == 0:
                            argtypes.append((type,))
                        else:
                            argtype = args.annotations[arg]
                            if not isinstance(argtype, tuple):
                                argtype = (argtype,)
                            argtypes.append(argtype)

                    result = args.annotations['return']

                    for argt in itertools.product(*argtypes):
                        TypeRules.add_rule(astop, argt, result)

        return result

    def __init__(cls, name, bases, dct, *, type):
        super().__init__(name, bases, dct)


class TypeInfo(metaclass=TypeInfoMeta, type=None):
    pass


class FunctionMeta(type):
    function_map = {}

    def __new__(mcls, name, bases, dct):
        result = super().__new__(mcls, name, bases, dct)

        get_signature = getattr(result, 'get_signature', None)

        signature = None
        if get_signature:
            signature = get_signature()

        if signature:
            signature = (signature[0], (signature[1],) if signature[1] else (), signature[2])
            TypeRules.add_rule(*signature)

        get_canonical_name = getattr(result, 'get_canonical_name', None)

        if get_canonical_name:
            canonical_name = get_canonical_name()
            mcls.function_map[canonical_name] = result

        return result

    @classmethod
    def get_function_class(mcls, name):
        return mcls.function_map.get(name)


class BaseTypeMeta:
    base_type_map = {}
    implementation_map = {}
    mixin_map = {}

    @classmethod
    def add_mapping(cls, type, caos_builtin_name):
        cls.base_type_map[type] = caos_builtin_name

    @classmethod
    def add_implementation(cls, caos_name, type):
        existing = cls.implementation_map.get(caos_name)
        if existing is not None:
            msg = ('cannot set {!r} as implementation: {!r} is already ' +
                   'implemented by {!r}').format(type, caos_name, existing)
            raise ValueError(msg)

        cls.implementation_map[caos_name] = type

    @classmethod
    def add_mixin(cls, caos_name, type):
        try:
            mixins = cls.mixin_map[caos_name]
        except KeyError:
            mixins = cls.mixin_map[caos_name] = []

        mixins.append(type)

    @classmethod
    def type_to_caos_builtin(cls, type):
        return cls.base_type_map.get(type)

    @classmethod
    def get_implementation(cls, caos_name):
        return cls.implementation_map.get(caos_name)

    @classmethod
    def get_mixins(cls, caos_name):
        mixins = cls.mixin_map.get(caos_name)
        return tuple(mixins) if mixins else tuple()


def proto_name_from_type(typ):
    """Return canonical prototype name for a given type.

    Arguments:

    - type             -- Type to normalize

    Result:

    Canonical prototype name.
    """

    is_composite = isinstance(typ, tuple)

    if is_composite:
        container_type = typ[0]
        item_type = typ[1]
    else:
        item_type = typ

    proto_name = None

    if item_type is None or item_type is type(None):
        proto_name = 'metamagic.caos.builtins.none'

    elif isinstance(item_type, so.ProtoNode):
        proto_name = item_type.name

    elif isinstance(item_type, s_pointers.Pointer):
        proto_name = item_type.name

    elif isinstance(item_type, so.PrototypeClass):
        proto_name = item_type

    else:
        proto_name = BaseTypeMeta.type_to_caos_builtin(item_type)

    if not proto_name:
        if isinstance(item_type, type):
            if hasattr(item_type, '__sx_prototype__'):
                proto_name = item_type.__sx_prototype__.name
        else:
            if hasattr(item_type.__class__, '__sx_prototype__'):
                proto_name = item_type.__class__.__sx_prototype__.name

    if proto_name is None:
        raise s_err.SchemaError(
            'could not find matching prototype for %r' % typ)

    if is_composite:
        result = (container_type, proto_name)
    else:
        result = proto_name

    return result


def normalize_type(type, proto_schema):
    """Normalize provided type description into a canonical prototype form.

    Arguments:

    - type             -- Type to normalize
    - proto_schema     -- Prototype schema to use for prototype lookups

    Result:

    Normalized type.
    """

    proto_name = proto_name_from_type(type)
    if proto_name is None:
        raise s_err.SchemaError(
            'could not find matching prototype for %r' % type)

    is_composite = isinstance(proto_name, tuple)

    if is_composite:
        container_type = proto_name[0]
        item_proto_name = proto_name[1]
    else:
        item_proto_name = proto_name

    if isinstance(item_proto_name, so.PrototypeClass):
        item_proto = item_proto_name
    else:
        item_proto = proto_schema.get(item_proto_name)

    if is_composite:
        result = (container_type, item_proto)
    else:
        result = item_proto

    return result
