# Reminis
A basic framework to memoize python functions between script executions.
Intended to speed up iteration times while developing data-processing scripts by caching processing-intensive steps to disk, so that they can be skipped on subsequent runs.

Requires python 3.7.

**Warning:** This is very much a work-in-progress intended mainly for personal use. I've made it available in case others find it useful as well, but use at your own risk.

## Quickstart
Make sure that a folder called `reminis_cache` exists in the folder you are running your main script from. (See [below](#cache-files).)
```
from reminis import compute, Proc

def add(a, b):
    return a + b

def mul(a, b):
    return a * b

result = compute([
    Proc(add, [2,5]),
    Proc(mul, [3])
])

print(result) # 21
``` 

See `dependencies_example.py` for an exmaple that shows more features.

## Concepts
Reminis takes in a number of _processors_, which get connected into a _pipeline_.

A processor is a function, taking inputs and arguments, and producing data in return. Arguments are user-provided along with the processor, while inputs are the outputs of other processors that a given processor depends on.
Processors are required to be pure. Specifically, they should always return the same value when passed the same inputs.

A pipeline is a graph of processors, connected up based on their dependencies. A pipeline can be computed to provide an output, which is the output of the last processor in the pipeline.  
Conceptually, the output is computed by walking up this graph, starting at the last processor, and running any processsors it is dependent on in order to get the inputs to pass to it. Those processors may in turn have dependencies, which will thus get run even earlier.

The main task of Reminis is to avoid actually computing the output of a processor by instead caching the results from a previous run and saving it to a file. Then, when the output of a processor is needed, and the cached data is valid for the inputs and arguments provided to the processor, it can simply be loaded from disk.

Cached data is considered valid if all inputs to a processor are valid, its code has not changed, and the inputs provided to it are the same as they were when the cached data was computed.  
(Currently, only code changes in the processor function are respected, changes in functions called by a processor are ignored. This is to be fixed in the future.)

Since computation of a pipeline works from the last processor backwards, computing and loading caches is avoided as much as possible. If a processor's cached data is valid, none of its dependencies are even computed or loaded.  
However, if any processor has changed and its cached data has become invalid, it will get recomputed. Consequently, any processors that take that data as input will also be recomputed in order to provide the correct overall output.

## Usage
The `compute` function takes a list of `Proc` objects, which describe the pipeline. It returns the output of the pipeline, doing as much caching as possible.

Every `Proc` object contains the actual processor function that computes the data for this processor.  
Optionally, it can contain:
- A list of arguments that should be passed to the processor function.
- A name to refer to it.
- A list of other processors it depends on .
- A few other settings for the behaviour of this processor.

The details of the `Proc` object are given below.

The pipeline is constructed based on the dependencies between the `Proc` objects provided. By default, ever processor depends on the processor before it in the list passed to `compute`. Thus, a simple linear pipeline is constructed just by passing a list of the processors in order.

For a more complex pipeline, list the dependencies of processors that need them in their `dependencies` property. Processors can be referred to by the name given in their `name` property, or the name of their processor function otherwise.

See `dependencies_example.py` for a simple setup of a pipeline that uses explicit dependencies to reuse the output of one processor for the input of multiple other processors.

## Details
`Proc` object

`processor`: function  
> The function that is run by this processor. 
  Must be a pure function.  
  All arguments to this are passed as positional arguments.  
  First, outputs of any dependencies are passed, in order of listing in `dependencies`.  
  Then, arguments from `args` are passed. 
  The output of this processor is simply the return value of this function.

`args`: list
> Positional arguments that should be passed to `processor`

`name`: str
> Name for this processor node. Used to refer to this processor in the `dependencies` list of other Proc nodes.

`dependencies`: list of strings
> The names of Proc nodes this node depends on.  
  A node's name is its `name` property if it is given, and the name of its `processor` function otherwise.  
  Only Proc nodes appearing before this one in the pipeline can be referenced.  
  One element of this list can be -1, to reference the node immediately before this one in the pipeline.

`impure`: bool
> If True, the function is always considered as changed, and thus re-computed every run.  
  Any dependents will consequently also re-run.
  The output of this processor is not cached.

`no_caching`: bool
> If True, the data produced by this processor is never cached, and instead always re-computed if needed.  
  Validity is still checked as normal.

## Cache files
Cache files are currently stored in a folder called `reminis_cache` in the folder that the script using reminis is being executed in.
For each processor, there are two files: the metadata cache, and the actual data cache. The metadata contains all the information needed to check a processor's validity, while the data cache contains the actual cached value. These are split up so that loading the (potentially large) data can be avoided if it's not required. 