



+ implementations for 
    + gradient descent 
    + [Two-Point Step Size Gradient Methods](https://academic.oup.com/imajna/article/8/1/141/802460) (gradient descent with Barzilai Borwein stepsize)
    + [A Method of Solving a Convex Programming Problem with Convergence Rate o(1/k^2)](http://mpawankumar.info/teaching/cdt-big-data/nesterov83.pdf) (Nesterov Accelerated Gradient)


## Resources

+ Optim.jl nonconvex optimization https://julianlsolvers.github.io/Optim.jl/stable/#
    + [Nesterov's correction](https://github.com/JuliaNLSolvers/Optim.jl/blob/master/src/multivariate/solvers/first_order/accelerated_gradient_descent.jl)
+ NAG impl 
    + https://github.com/GRYE/Nesterov-accelerated-gradient-descent/blob/master/nesterov_method.py
    + https://github.com/idc9/optimization_algos/blob/master/opt_algos/accelerated_gradient_descent.py

## Setup

```
# setup julia https://github.com/mitmath/julia-mit
# Install julia v1.0.5 @ https://julialang.org/downloads/

# Open julia repl
$ julia

# Enter package mode
julia> ]

# Activate package 
(v0.7) pkg> activate .

# Download dependencies
(opt) pkg> instantiate

# Update package and precompile modules
(opt) pkg> update; precompile

# Back to julia repl, and start hacking!
julia> using opt

# condigure PyCall to use conda envs
julia> ENV["PYTHON"] = "/data/vision/polina/shared_software/miniconda3/envs/misc_impl"
(opt) pkg> build Conda
```

```
# IJulia https://github.com/JuliaLang/IJulia.jl
# Install additional julia kernel, i.e. pass cmd args
using IJulia
installkernel("Julia nodeps", "--depwarn=no")
installkernel("Julia (4 threads)", env=Dict("JULIA_NUM_THREADS"=>"4"))
```