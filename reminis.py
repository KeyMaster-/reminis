from dataclasses import dataclass, field
from typing import Any, Callable
import pickle
import inspect
from hashlib import md5
from inspect import signature, getsource

# pipeline: list of Proc objects
def compute(pipeline):
    tree = make_pipeline_tree(pipeline)

    return get_data(tree)

### Input processor class
# processor: function
#   The function that is run by this processor. 
#   Must be a pure function. 
#   All arguments to this are passed as positional arguments. 
#   First, outputs of any dependencies are passed, in order of listing in `dependencies`. 
#   Then, arguments from `args` are passed. 
#   The output of this processor is simply the return value of this function.
#
# args: list
#   Positional arguments that should be passed to `processor`
#
# name: str
#   Name for this processor node. Used to refer to this processor in the `dependencies` list of other Proc nodes.
#
# dependencies: list of strings
#   The names of Proc nodes this node depends on. 
#   A node's name is its `name` property if it is given, and the name of its `processor` function otherwise.
#   Only Proc nodes appearing before this one in the pipeline can be referenced.
#   One element of this list can be -1, to reference the node immediately before this one in the pipeline.
#
# calls: list of functions
#   A list of functions called by `processor`.
#   Changes in the code of these functions will also invalidate this processor.
#
# impure: bool
#   If True, the function is always considered as changed, and thus re-computed every run.
#   Any dependents will consequently also re-run.
#   The output of this processor is not cached.
#
# no_caching: bool
#   If True, the data produced by this processor is never cached, and instead always re-computed if needed.
#   Validity is still checked as normal.

@dataclass
class Proc:
    processor: Callable
    args: list = field(default_factory=list)
    name: str = None
    dependencies: list = None #list of names referencing previous Proc instances in pipeline
    calls: list = field(default_factory=list)
    impure: bool = False
    no_caching: bool = False

### Internal processor node
# processor, args, name, impure, no_caching
#   See corresponding properties on Proc
#
# dependencies: list of ProcessorNodes
#   The internal ProcessorNode instances corresponding to the Proc nodes referred to by Proc.dependencies
#
# data: any
#   The return data of this function's `processor`, if it has been computed during this run.
#
# valid: bool
#   Whether this processor is valid, meaning whether its value needs to be re-computed this run.
@dataclass
class ProcessorNode:
    processor: Callable
    args: list
    name: str
    impure: bool
    no_caching: bool
    dependencies: list # list of ProcessorNode, but type can't refer to itself it seems
    calls: list
    data: Any
    valid: bool

def get_path(node, meta):
    caching_folder = "reminis_cache/"

    node_name = get_node_name(node)

    ending = (".meta" if meta else "") + ".cache"

    return caching_folder + node_name + ending

    # compute a hash for a list of functions
def functions_hash(functions):
    hasher = md5()

    for f in functions:
        # bytecode does not change when only constants change, so it is not enough to detect function change
        # using the actual source is less efficient and is overly conservative, but it's better than missing changes
        hasher.update(getsource(f).encode('utf-8'))

    return hasher.digest()

def make_meta(node):
        # hashes of dependency functions are used to check that this node is still connnected to the same inputs
    dep_hashes = [functions_hash([dep.processor]) for dep in node.dependencies]
    src_hash = functions_hash([node.processor] + node.calls)

    return {
        "src_hash": src_hash,
        "dep_hashes": dep_hashes,
        "pos_args": node.args
    }

    # todo: changes in constants in a function don't change the bytecode
    # maybe just go to hash of source code for now?
def meta_eq(meta1, meta2):
    pos_args1 = meta1["pos_args"]
    pos_args2 = meta2["pos_args"]

    if pos_args1 != pos_args2:
        # print("pos args not equal")
        return False

    src_hash1 = meta1["src_hash"]
    src_hash2 = meta2["src_hash"]

    if src_hash1 != src_hash2:
        # print("src hashes not equal")
        return False

    dep_hashes1 = meta1["dep_hashes"]
    dep_hashes2 = meta2["dep_hashes"]

    if dep_hashes1 != dep_hashes2:
        # print("dep hashes not equal")
        return False

    return True

def run_processor(processor, args, inputs):
    new_args = inputs + args
    processor_sig = signature(processor)

    # if len(new_args) != len(processor_sig.parameters):
    #     print(f"Processor {processor} requires {len(processor_sig.parameters)} parameters, but was given {len(new_args)}")

    return processor(*new_args)

def gen_and_cache(node):
    inputs = [get_data(dep) for dep in node.dependencies]

    data = run_processor(node.processor, node.args, inputs)
    
    meta = make_meta(node)
    meta_path = get_path(node, True)
    f = open(meta_path, "wb")
    pickle.dump(meta, f)
    f.close()

        # if we don't cache data, we still need to write metadata, to check wether future invocations
        # do or do not invalidate their dependants
    if node.no_caching:
        return data

    data_path = get_path(node, False)
    f = open(data_path, "wb")
    pickle.dump(data, f)
    f.close()
    return data

def node_valid(node):
        # always treat impure nodes as invalid
    if node.impure:
        return False

        # if we already checked validity, reuse that value
    if node.valid != None:
        return node.valid

        # a node is only valid if dependencies are valid
    valid = True
    for dep in node.dependencies:
        valid = valid and node_valid(dep)

    # print(f"{node.processor[0].__name__} / deps valid: {valid}")

    if not valid:
        node.valid = False
        return False

    meta_path = get_path(node, True)
    # print(meta_path)

    meta_data = None
    try:
        f = open(meta_path, "rb")
        meta_data = pickle.load(f)
        f.close()
        # print(f"{node.processor[0].__name__} / meta found")
    except FileNotFoundError:
            # if no metadata is on file, node is not valid (we have nothing to check parameters against)
        node.valid = False
        return False

    new_meta = make_meta(node)

        # if the new paramters don't match what's cached, this node is not valid
    if not meta_eq(new_meta, meta_data):
        # print('meta not eq')
        node.valid = False
        # print(f"{node.processor[0].__name__} / meta not equal")
        return False

    # print(new_meta["src_hash"], meta_data["src_hash"])
    # print('meta eq')

    node.valid = True
    return True

def get_data(node):
    valid = node_valid(node)
    # print(f"{node.processor[0].__name__} / not valid")

        # if we generated the data this run, it's definitely correct
    if node.data is not None:
        return node.data

    data = None

        # if we don't have data in memory, try to load it from disk
    if valid and not node.no_caching:
        data_path = get_path(node, False)
        try:
            f = open(data_path, "rb")
            data = pickle.load(f)
            f.close()
        except FileNotFoundError:
            pass
            
        # we got data, so return it
    if data is not None:
        return data

        # no data found, or this node is invalid, so we need to generate it
    data = gen_and_cache(node)
    node.data = data

    return data

def find_by_name(tree, name):
    if tree.name == name:
        return tree

    for dep in tree.dependencies:
        found_node = find_by_name(dep, name)
        if found_node is not None:
            return found_node

    return None

    # expected to work on Proc and ProcessorNode
def get_node_name(node):
    if node.name is not None:
        return node.name

    return node.processor.__name__

def make_pipeline_tree(pipeline):
    nodes = []

    for i in range(len(pipeline)):
        proc = pipeline[i]

        dependencies = []
        if proc.dependencies is not None:

            for dep_ref in proc.dependencies:
                dep_node = None

                if isinstance(dep_ref, str):
                    for node in nodes:
                        if node.name == dep_ref:
                            dep_node = node
                            break
                else:
                    if not isinstance(dep_ref, int):
                        print("Can't have dependency references of types other than strings or ints")
                    elif dep_ref != -1:
                        print("Can only reference the previous processor by index.")
                    else:
                        dep_node = nodes[-1]

                if dep_node is None:
                    print(f"No node with reference {dep_ref} exists before node {get_node_name(proc)}")
                else:
                    dependencies.append(dep_node)
        else:
            if len(nodes) > 0:
                dependencies.append(nodes[-1])

        node = ProcessorNode(proc.processor, proc.args, get_node_name(proc), proc.impure, proc.no_caching, dependencies, proc.calls, None, None)
        nodes.append(node)

    return nodes[-1]

