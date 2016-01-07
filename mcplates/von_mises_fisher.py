import numpy as np
import scipy.stats as st

from pymc3.distributions import Continuous
from pymc3.distributions.distribution import draw_values, generate_samples
from pymc3.distributions.dist_math import bound

import theano.tensor
import theano

d2r = np.pi/180.
r2d = 180./np.pi
eps = 1.e-6

def construct_euler_rotation_matrix(alpha, beta, gamma):
    """
    Make a 3x3 matrix which represents a rigid body rotation,
    with alpha being the first rotation about the z axis,
    beta being the second rotation about the y axis, and
    gamma being the third rotation about the z axis.
 
    All angles are assumed to be in radians
    """
    rot_alpha = np.array( [ [np.cos(alpha), -np.sin(alpha), 0.],
                            [np.sin(alpha), np.cos(alpha), 0.],
                            [0., 0., 1.] ] )
    rot_beta = np.array( [ [np.cos(beta), 0., np.sin(beta)],
                           [0., 1., 0.],
                           [-np.sin(beta), 0., np.cos(beta)] ] )
    rot_gamma = np.array( [ [np.cos(gamma), -np.sin(gamma), 0.],
                            [np.sin(gamma), np.cos(gamma), 0.],
                            [0., 0., 1.] ] )
    rot = np.dot( rot_gamma, np.dot( rot_beta, rot_alpha ) )
    return rot
    

class VonMisesFisher(Continuous):
    """
    Von Mises-Fisher distribution

    Parameters
    ----------

    mu : cartesian unit vector representing
        the mean direction
    kappa : floating point number representing the
        spread of the distribution.
    """

    def __init__(self, lon_colat, kappa, *args, **kwargs):
        super(VonMisesFisher, self).__init__(shape=2, *args, **kwargs)

        assert(theano.tensor.ge(kappa,0.))

        lon = lon_colat[0]*d2r
        colat = lon_colat[1]*d2r
        self.lon_colat = lon_colat
        self.mu = [ theano.tensor.sin(colat) * theano.tensor.cos(lon),
                    theano.tensor.sin(colat) * theano.tensor.sin(lon),
                    theano.tensor.cos(colat) ]
        self.kappa = kappa
        self.median = self.mode = self.mean = lon_colat

    def random(self, point=None, size=None):
        lon_colat, kappa = draw_values([self.lon_colat, self.kappa], point=point)
        # make the appropriate euler rotation matrix
        rotation_matrix = construct_euler_rotation_matrix(0., lon_colat[1]*d2r, lon_colat[0]*d2r)

        def cartesian_sample_generator(size=None):
            # Generate samples around the z-axis, then rotate
            # to the appropriate position using euler angles

            # z-coordinate is determined by inversion of the cumulative
            # distribution function for that coordinate.
            zeta = st.uniform.rvs(loc=0., scale=1., size=size)
            if kappa < eps:
                z = 2.*zeta-1.
            else:
                z = 1. + 1./kappa * np.log(zeta + (1.-zeta)*np.exp(-2.*kappa) )

            # x and y coordinates can be determined by a 
            # uniform distribution in longitude.
            phi = st.uniform.rvs(loc=0., scale=2.*np.pi, size=size)
            x = np.sqrt(1.-z*z)*np.cos(phi)
            y = np.sqrt(1.-z*z)*np.sin(phi)

            # Rotate the samples to have the correct mean direction
            unrotated_samples = np.vstack([x,y,z])
            samples = np.transpose(np.dot(rotation_matrix, unrotated_samples))
            return samples
            
        cartesian_samples = cartesian_sample_generator(size) 
        colat_samples = np.fromiter( (np.arccos( s[2]/np.sqrt(np.dot(s,s)) ) for s in cartesian_samples), dtype=np.float64, count=size)
        lon_samples = np.fromiter( (np.arctan2( s[1], s[0] ) for s in cartesian_samples), dtype=np.float64, count=size)
        return np.transpose(np.vstack((lon_samples, colat_samples)))*r2d

    def logp(self, lon_colat):
        kappa = self.kappa
        mu = self.mu
        lon_colat_r = theano.tensor.reshape( lon_colat*d2r, (-1, 2) )
        point = [ theano.tensor.sin(lon_colat_r[:,1]) * theano.tensor.cos(lon_colat_r[:,0]),
                  theano.tensor.sin(lon_colat_r[:,1]) * theano.tensor.sin(lon_colat_r[:,0]),
                  theano.tensor.cos(lon_colat_r[:,1]) ]
        point = theano.tensor.as_tensor_variable(point).T

        return bound( theano.tensor.switch( theano.tensor.ge(kappa, eps), \
                                             # Kappa greater than zero
                                             theano.tensor.log( -kappa / ( 2.*np.pi * theano.tensor.expm1(-2.*kappa)) ) + \
                                             kappa * (theano.tensor.dot(point,mu)-1.),
                                             # Kappa equals zero
                                             theano.tensor.log(1./4./np.pi)),
                      theano.tensor.all( lon_colat_r[:,1] >= 0. ),
                      theano.tensor.all( lon_colat_r[:,1] <= np.pi ) )