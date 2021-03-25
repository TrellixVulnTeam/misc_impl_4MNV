import math
from typing import Any, Callable, Sequence, Optional, Tuple

import jax
from jax import random
import jax.numpy as np
import jax.numpy.linalg as linalg
from jax.scipy.linalg import cho_solve, solve_triangular

import flax
from flax.core import unfreeze
from flax import optim
from flax import linen as nn

from jaxkern import cov_se, sqdist


class CovSE(nn.Module):

    def setup(self):
        self.transform = BijectiveSoftplus()
        init_fn = lambda k, s: self.transform.reverse(np.array([1.]))
        self.ℓ  = self.transform.forward(self.param('ℓ',  init_fn, (1,)))
        self.σ2 = self.transform.forward(self.param('σ2', init_fn, (1,)))
        
    def scale(self, X):
        return X/self.ℓ if X is not None else X

    def __call__(self, X, Y=None, diag=False):
        if diag:
            return np.tile(self.σ2, len(X))
        else:
            X = self.scale(X)
            Y = self.scale(Y)
            return self.σ2*np.exp(-sqdist(X, Y)/2)



class GPR(nn.Module):
    data: Tuple[np.ndarray, np.ndarray]
        
    def setup(self):
        self.k = CovSE()
        self.lik = LikNormal()
        
    def get_init_params(self, key):
        params = self.init(key, np.ones((1, self.data[0].shape[-1])),
                           method=self.pred_f)
        return params

    def mll(self):
        X, y = self.data
        k = self.k
        n = len(X)
        
        K = k(X) + self.lik.σ2*np.eye(n)
        L = linalg.cholesky(K)
        α = cho_solve((L, True), y)

        mll_quad  = -(1/2)*np.sum(y*α)
        mll_det   = - np.sum(np.log(np.diag(L)))
        mll_const = - (n/2)*np.log(2*np.pi)
        mll = mll_quad + mll_det + mll_const

        return mll
    
    def pred_f(self, Xs):
        X, y = self.data
        k = self.k
        n = len(X)
        
        K = k(X) + self.lik.σ2*np.eye(n)
        Ks = k(X, Xs)
        Kss = k(Xs, Xs)
        L = linalg.cholesky(K)
        α = cho_solve((L, True), y)
        μ = Ks.T@α
        v = solve_triangular(L, Ks, lower=True)
        Σ = Kss - v.T@v
        
        return μ, Σ
    
    def pred_y(self, Xs):
        μf, Σf = self.pred_f(Xs)
        ns = len(Σf)
        μy, Σy = μf, Σf + self.lik.σ2*np.diag(np.ones((ns,)))
        return μy, Σy


class GPRFITC(nn.Module):
    data: Tuple[np.ndarray, np.ndarray]
    n_inducing: int

    def setup(self):
        self.k = CovSE()
        self.lik = LikNormal()
        X, y = self.data
        self.Xu = self.param('Xu', lambda k,s : X[:self.n_inducing],
                             (self.n_inducing, X.shape[-1]))

    def get_init_params(self, key):
        params = self.init(key, np.ones((1, self.data[0].shape[-1])),
                           method=self.pred_f)
        return params
    
    def precompute(self):
        X, y = self.data
        k = self.k
        Xu = self.Xu
        n, m = len(X), self.n_inducing
        
        Kdiag = k(X, diag=True)
        Kuu = k(Xu, Xu)
        Kuf = k(Xu, X)
        Luu = cholesky_jitter(Kuu, jitter=1e-4)
        
        V = solve_triangular(Luu, Kuf, lower=True)
        Qffdiag = np.sum(np.square(V), axis=0)
        Λ = Kdiag - Qffdiag + self.lik.σ2
        Λ = Λ.reshape(-1,1)
        
        B = np.eye(m) + (V/Λ.T)@V.T
        LB = cholesky_jitter(B, jitter=1e-5)
        γ = solve_triangular(LB, V@(y/Λ), lower=True)

        return Luu, Λ, LB, γ
    
    def mll(self):
        X, y = self.data
        n = len(X)
        Luu, Λ, LB, γ = self.precompute()
        
        mll_quad  = -.5*( np.sum((y/Λ)*y) - np.sum(np.square(γ)) )
        mll_det   = -np.sum(np.log(np.diag(LB)))-.5*np.sum(np.log(Λ))
        mll_const = -(n/2)*np.log(2*np.pi)
        mll = mll_quad + mll_det + mll_const

        return mll
    
    def pred_f(self, Xs):
        X, y = self.data
        k = self.k
        Xu = self.Xu
        n = len(X)
        Luu, Λ, LB, γ = self.precompute()
        
        Kss = k(Xs, Xs)
        Kus = k(Xu, Xs)
        ω = solve_triangular(Luu, Kus, lower=True)
        ν = solve_triangular(LB, ω, lower=True)
        
        μ = ω.T@solve_triangular(LB.T, γ, lower=False)
        Σ = Kss - ω.T@ω + ν.T@ν
        
        return μ, Σ

    def pred_y(self, Xs):
        μf, Σf = self.pred_f(Xs)
        ns = len(Σf)
        μy, Σy = μf, Σf + self.lik.σ2*np.diag(np.ones((ns,)))
        return μy, Σy


class VFE(nn.Module):
    data: Tuple[np.ndarray, np.ndarray]
    n_inducing: int

    def setup(self):
        self.k = CovSE()
        self.lik = LikNormal()
        X, y = self.data
        self.Xu = self.param('Xu', lambda k,s : X[:self.n_inducing],
                             (self.n_inducing, X.shape[-1]))

    def get_init_params(self, key):
        params = self.init(key, np.ones((1, self.data[0].shape[-1])),
                           method=self.pred_f)
        return params
    
    def precompute(self):
        X, y = self.data
        k = self.k
        Xu = self.Xu
        n, m = len(X), self.n_inducing
        
        Kdiag = k(X, diag=True)
        Kuu = k(Xu, Xu)
        Kuf = k(Xu, X)
        Luu = cholesky_jitter(Kuu, jitter=1e-4)
        
        V = solve_triangular(Luu, Kuf, lower=True)
        Qffdiag = np.sum(np.square(V), axis=0)
        Λ = Kdiag - Qffdiag + self.lik.σ2
        Λ = Λ.reshape(-1,1)
        
        B = np.eye(m) + (V/Λ.T)@V.T
        LB = cholesky_jitter(B, jitter=1e-5)
        γ = solve_triangular(LB, V@(y/Λ), lower=True)

        return Kdiag, Luu, V, Λ, LB, γ
    
    def mll(self):
        X, y = self.data
        n = len(X)
        Kdiag, Luu, V, Λ, LB, γ = self.precompute()
        
        elbo_quad  = -.5*( np.sum((y/Λ)*y) - np.sum(np.square(γ)) )
        elbo_det   = -np.sum(np.log(np.diag(LB)))-.5*np.sum(np.log(Λ))
        elbo_const = -(n/2)*np.log(2*np.pi)
        elbo_trcc  = -(1/2/self.lik.σ2[0])*( np.sum(Kdiag) - np.sum(np.square(V)) )
        
        elbo = elbo_quad + elbo_det + elbo_const + elbo_trcc
        return elbo
    
    def pred_f(self, Xs):
        X, y = self.data
        k = self.k
        Xu = self.Xu
        n = len(X)
        Kdiag, Luu, V, Λ, LB, γ = self.precompute()
        
        Kss = k(Xs, Xs)
        Kus = k(Xu, Xs)
        ω = solve_triangular(Luu, Kus, lower=True)
        ν = solve_triangular(LB, ω, lower=True)
        
        μ = ω.T@solve_triangular(LB.T, γ, lower=False)
        Σ = Kss - ω.T@ω + ν.T@ν
        
        return μ, Σ

    def pred_y(self, Xs):
        μf, Σf = self.pred_f(Xs)
        ns = len(Σf)
        μy, Σy = μf, Σf + self.lik.σ2*np.diag(np.ones((ns,)))
        return μy, Σy


class BijectiveExp(object):
    
    @staticmethod
    def forward(x):
        """ x -> exp(x) \in \R+ """
        return np.exp(x)
    
    @staticmethod
    def reverse(y):
        return np.log(y)


class BijectiveSoftplus(object):
    # Reference
    # - https://www.tensorflow.org/probability/api_docs/python/tfp/bijectors/Softplus
    # - http://num.pyro.ai/en/stable/_modules/numpyro/distributions/transforms.html
    @staticmethod
    def forward(x):
        """ x -> log(1+exp(x)) \in \R+ """
        return jax.nn.softplus(x)
    
    @staticmethod
    def reverse(y):
        """ y -> log(exp(y)-1)
                 log(1-exp(-y))+log(exp(y))
                 log(1-exp(-y))+y
        """
        return np.log(-np.expm1(-y)) + y


class BijectiveFillTril(object):
    """Transofrms vector to lower triangular matrix
            v (n,) -> L (m,m)
                where `m = (-1+sqrt(1+8*n))/2`
                      `n = m*(m+1)/2`.`
                      
        ```
            v = np.arange(6)
            L = FillTril.forward(v)
            w = FillTril.reverse(L)
            print(L, w)
            # [[0. 0. 0.]
            #  [1. 2. 0.]
            #  [3. 4. 5.]]
            # [0. 1. 2. 3. 4. 5.]
        ```

        Reference
        - https://www.tensorflow.org/probability/api_docs/python/tfp/bijectors/FillTriangular
        - https://www.tensorflow.org/probability/api_docs/python/tfp/math/fill_triangular
    """
    @staticmethod
    def forward_shape(n):
        return int((-1+math.sqrt(1+8*n))/2)
    
    @staticmethod
    def reverse_shape(m):
        return int(m*(m+1)/2)
    
    @staticmethod
    def forward(v):
        m = BijectiveFillTril.forward_shape(v.size)
        L = np.zeros((m,m))
        L = jax.ops.index_update(L, np.tril_indices(m), v.squeeze())
        return L
    
    @staticmethod
    def reverse(L):
        m = len(L)
        v = L[np.tril_indices(m)]
        v = v.reshape(-1,1)
        return v


def kl_mvn(μ0, Σ0, μ1, Σ1):
    """KL(q||p) where q~N(μ0,Σ0), p~N(μ1,Σ1) """
    n = μ0.size
    kl_trace = np.trace(linalg.solve(Σ1, Σ0))
    kl_mahan = np.sum((μ1-μ0).T@linalg.solve(Σ1, (μ1-μ0)))
    kl_const = -n
    kl_lgdet = np.log(linalg.det(Σ1)) - np.log(linalg.det(Σ0))
    kl = .5*( kl_trace + kl_mahan + kl_const + kl_lgdet )
    return kl


def kl_mvn_tril(μ0, L0, μ1, L1):
    """KL(q||p) where q~N(μ0,L0@L0.T), p~N(μ1,L1@L1.T) 
    
        ```
            def rand_μΣ(key, m):
                μ = random.normal(key, (m,1))
                Σ = random.normal(key, (m,m))
                Σ = jax.ops.index_update(Σ, np.tril_indices(m), 0)
                Σ = Σ@Σ.T+0.1*np.eye(m)
                return μ,Σ
            m = 50
            μ0,Σ0 = rand_μΣ(jax.random.PRNGKey(0), m)
            μ1,Σ1 = rand_μΣ(jax.random.PRNGKey(1), m)
            μ1 = np.zeros((m,1))
            L0 = linalg.cholesky(Σ0)
            L1 = linalg.cholesky(Σ1)
            print(kl_mvn(μ0, Σ0, μ1, Σ1))
            print(kl_mvn_tril(μ0, L0, μ1, L1))
            print(kl_mvn_tril_zero_mean_prior(μ0, L0, L1))
        ```
    """
    n = μ0.size
    α = solve_triangular(L1, L0, lower=True)
    β = solve_triangular(L1, μ1 - μ0, lower=True)
    kl_trace = np.sum(np.square(α))
    kl_mahan = np.sum(np.square(β))
    kl_const = -n
    kl_lgdet = 2*(np.sum(np.log(np.diag(L1))) - np.sum(np.log(np.diag(L0))))
    kl = .5*( kl_trace + kl_mahan + kl_const + kl_lgdet )
    return kl

def kl_mvn_tril_zero_mean_prior(μ0, L0, L1):
    """KL(q||p) where q~N(μ0,L0@L0.T), p~N(0,L1@L1.T) """
    n = μ0.size
    α = solve_triangular(L1,  L0, lower=True)
    β = solve_triangular(L1, -μ0, lower=True)
    kl_trace = np.sum(np.square(α))
    kl_mahan = np.sum(np.square(β))
    kl_const = -n
    kl_lgdet = 2*(np.sum(np.log(np.diag(L1))) - np.sum(np.log(np.diag(L0))))
    kl = .5*( kl_trace + kl_mahan + kl_const + kl_lgdet )
    return kl

def cholesky_jitter(K, jitter=1e-6):
    L = linalg.cholesky(K+jitter*np.eye(len(K)))
    return L


def randsub_init_fn(key, shape, dtype=np.float32, X=None):
    idx = random.choice(key, np.arange(len(X)),
                        shape=(shape[0],), replace=False)
    return X[idx]


proc_leaf_scalar_exponentiate = lambda k, v: \
    (k.split('log')[1], np.exp(v[0])) if (k.startswith('log') and v.size==1) else (k, v)
proc_leaf_vector_exponentiate = lambda k, v: \
    (k.split('log')[1], np.exp(v)) if (k.startswith('log') and v.size>1) else (k, v)
PROC_LEAF_VECTOR_LENGTH_LIMIT = 5
proc_leaf_vector_firstn = lambda k, v: \
    (f'{k}[:{PROC_LEAF_VECTOR_LENGTH_LIMIT}]', v[:PROC_LEAF_VECTOR_LENGTH_LIMIT]) \
        if isinstance(v, np.ndarray) and v.size>1 else (k, v)
proc_leaf_vector_squeeze = lambda k, v: \
    (k, v.squeeze()) if isinstance(v, np.ndarray) else (k, v)
prof_leaf_fns = [proc_leaf_scalar_exponentiate,
                 proc_leaf_vector_exponentiate,
                 proc_leaf_vector_firstn,
                 proc_leaf_vector_squeeze]

def log_func_simple(i, f, params, everyn=10):
    if i%everyn==0:
        print(f'[{i:3}]\tLoss={f(params):.3f}')


def log_func_default(i, f, params, everyn=20):
    if i%everyn == 0:
        flattened = flax.traverse_util.flatten_dict(unfreeze(params['params']))
        S = []
        for k, v in flattened.items():
            lk = k[-1]
            for proc in prof_leaf_fns:
                lk, v = proc(lk, v)
            k = list(k)
            k[-1] = lk
            k = '.'.join(k)
            S.append(f'{k}={v:.3f}' if v.size==1 else f'{k}={v}')

        S = '\t'.join(S)
        print(f'[{i:3}]\tLoss={f(params):.3f}\t{S}')


def flax_create_optimizer(params, optimizer, optimizer_kwargs):
    optimizer_cls = getattr(optim, optimizer)
    return optimizer_cls(**optimizer_kwargs).create(params)


def flax_run_optim(f, params, num_steps=10, log_func=None,
                   optimizer='GradientDescent',
                   optimizer_kwargs={'learning_rate': .002}):
    import itertools
    fg_fn = jax.value_and_grad(f)
    opt = flax_create_optimizer(
        params, optimizer=optimizer, optimizer_kwargs=optimizer_kwargs)
    itercount = itertools.count()
    for i in range(num_steps):
        fx, grad = fg_fn(opt.target)
        opt = opt.apply_gradient(grad)
        if log_func is not None: log_func(i, f, opt.target)
    return opt.target


def is_psd(x):
    return np.all(linalg.eigvals(x) > 0)