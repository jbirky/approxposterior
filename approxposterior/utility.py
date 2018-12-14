# -*- coding: utf-8 -*-
"""

Utility functions

"""

from __future__ import (print_function, division, absolute_import,
                        unicode_literals)

# Tell module what it's allowed to import
__all__ = ["logsubexp","AGPUtility","BAPEUtility","minimizeObjective",
           "functionWrapper","klNumerical"]

import numpy as np
from scipy.optimize import minimize


################################################################################
#
# Useful classes
#
################################################################################


class functionWrapper(object):
    """
    Wrapper class for functions.
    """

    def __init__(self, f, *args, **kwargs):
        """
        Initialize!
        """

        # Need function, optional args and kwargs
        self.f = f
        self.args = args
        self.kwargs = kwargs
    # end function


    def __call__(self, x):
        """
        Call the function on some input x.
        """

        return self.f(x, *self.args, **self.kwargs)
    # end function
# end class


################################################################################
#
# Define math functions
#
################################################################################


def klNumerical(x, p, q):
    """
    Estimate the KL-Divergence between pdfs p and q via Monte Carlo intergration
    using x, samples from p.

    KL ~ 1/n * sum_{i=1,n}(log (p(x_i)/q(x_i)))

    For our purposes, q is the current estimate of the pdf
    while p is the previous estimate.  This method is the
    only feasible method for large dimensions.

    See Hershey and Olsen, "Approximating the Kullback Leibler
    Divergence Between Gaussian Mixture Models" for more info

    Note that this method can result in D_kl < 0 but it's the only method with
    convergence properties as the number of samples (len(x)) grows.  Also, this
    method is shown to have the lowest error, on average (see Hershey and Olsen).

    Parameters
    ----------
    x : array
        Samples drawn from p
    p : function
        Callable previous estimate of the density
    q : function
        Callable current estimate of the density

    Returns
    -------
    kl : float
        KL divergence
    """
    try:
        res = np.sum(np.log(p(x)/q(x)))/len(x)
    except ValueError:
        errMsg = "ERROR: inf/NaN encountered.  q(x) = 0 likely occured."
        raise ValueError(errMsg)

    return res
# end function


def logsubexp(x1, x2):
    """
    Numerically stable way to compute log(exp(x1) - exp(x2))

    logsubexp(x1, x2) -> log(exp(x1) - exp(x2))

    Parameters
    ----------
    x1 : float
    x2 : float

    Returns
    -------
    logsubexp(x1, x2)
    """

    if x1 <= x2:
        return -np.inf
    else:
        return x1 + np.log(1.0 - np.exp(x2 - x1))
# end function


################################################################################
#
# Define utility functions
#
################################################################################


def AGPUtility(theta, y, gp):
    """
    AGP (Adaptive Gaussian Process) utility function, the entropy of the
    posterior distribution. This is what you maximize to find the next x under
    the AGP formalism. Note here we use the negative of the utility function so
    minimizing this is the same as maximizing the actual utility function.

    See Wang & Li (2017) for derivation/explaination.

    Parameters
    ----------
    theta : array
        parameters to evaluate
    y : array
        y values to condition the gp prediction on.
    gp : george GP object

    Returns
    -------
    u : float
        utility of theta under the gp
    """

    # Only works if the GP object has been computed, otherwise you messed up
    if gp.computed:
        mu, var = gp.predict(y, theta.reshape(1,-1), return_var=True)
    else:
        raise RuntimeError("ERROR: Need to compute GP before using it!")

    try:
        util = -(mu + 1.0/np.log(2.0*np.pi*np.e*var))
    except ValueError:
        print("Invalid util value.  Negative variance or inf mu?")
        raise ValueError("util: %e. mu: %e. var: %e" % (util, mu, var))

    return util
# end function


def BAPEUtility(theta, y, gp):
    """
    BAPE (Bayesian Active Posterior Estimation) utility function.  This is what
    you maximize to find the next theta under the BAPE formalism.  Note here we
    use the negative of the utility function so minimizing this is the same as
    maximizing the actual utility function.  Also, we log the BAPE utility
    function as the log is monotonic so the minima are equivalent.

    See Kandasamy et al. (2015) for derivation/explaination.

    Parameters
    ----------
    theta : array
        parameters to evaluate
    y : array
        y values to condition the gp prediction on.
    gp : george GP object

    Returns
    -------
    u : float
        utility of theta under the gp
    """

    # Only works if the GP object has been computed, otherwise you messed up
    if gp.computed:
        mu, var = gp.predict(y, theta.reshape(1,-1), return_var=True)
    else:
        raise RuntimeError("ERROR: Need to compute GP before using it!")

    try:
        util = -((2.0*mu + var) + logsubexp(var, 0.0))
    except ValueError:
        print("Invalid util value.  Negative variance or inf mu?")
        raise ValueError("util: %e. mu: %e. var: %e" % (util, mu, var))

    return util
# end function


def minimizeObjective(fn, y, gp, sampleFn, priorFn, bounds=None, **kw):
    """
    Find point that minimizes fn for a gaussian process gp conditioned on y,
    the data.

    Parameters
    ----------
    fn : function
        function to minimize that expects x, y, gp as arguments aka fn looks
        like fn_name(x, y, gp).  See *_utility functions above for examples.
    y : array
        y values to condition the gp prediction on.
    gp : george GP object
    sampleFn : function
        Function to sample initial conditions from.
    priorFn : function
        Function to apply prior to.
    kw : dict (optional)
        Any additional keyword arguments scipy.optimize.minimize could use,
        e.g., method.
    bounds : tuple/iterable (optional)
        Bounds for minimization scheme.  See scipy.optimize.minimize details
        for more information.  Defaults to None.

    Returns
    -------
    theta : (1 x n_dims)
        point that minimizes fn
    """

    is_finite = False
    while not is_finite:
        # Solve for theta that maximize fn and is allowed by prior

        # Choose theta0 by uniformly sampling over parameter space
        theta0 = sampleFn(1).reshape(1,-1)

        args=(y, gp)

        # Mimimze fn, see if prior allows solution
        try:
            tmp = minimize(fn, theta0, args=args, bounds=bounds,
                           method="l-bfgs-b", options={"ftol" : 1.0e-3},
                           **kw)["x"]

        # ValueError.  Try again.
        except ValueError:
            tmp = np.array([np.inf for ii in range(theta0.shape[-1])]).reshape(theta0.shape)

        # Vet answer: must be finite, allowed by prior
        # Are all values finite?
        if np.all(np.isfinite(tmp)):
            # Is this point in parameter space allowed by the prior?
            if np.isfinite(priorFn(tmp)):
                theta = tmp
                is_finite = True
    # end while

    return np.array(theta).reshape(1,-1)
# end function
