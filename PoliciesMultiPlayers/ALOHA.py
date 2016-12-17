# -*- coding: utf-8 -*-
""" ALOHA: generalized implementation of the single-player policy from [Concurrent bandits and cognitive radio network, O.Avner & S.Mannor, 2014](https://arxiv.org/abs/1404.5421).

This policy uses the collision avoidance mechanism that is inspired by the classical ALOHA protocol, and any single player policy.
"""
from __future__ import print_function

__author__ = "Lilian Besson"
__version__ = "0.1"

import numpy as np
import numpy.random as rn

from .BaseMPPolicy import BaseMPPolicy
from .ChildPointer import ChildPointer


# --- Functions to define tnext intervals

def tnext_beta(t, beta=0.5):
    """ Simple function, as used in MEGA: upper_tnext(t) = t ** beta. Default to t ** 0.5. """
    return t ** beta


def tnext_log(t, scaling=1.):
    """ Other function, not the one used in MEGA, but our proposal: upper_tnext(t) = scaling * log(t). """
    return scaling * np.log(t)


# --- Class oneALOHA, for children

class oneALOHA(ChildPointer):
    """ Class that acts as a child policy, but in fact it pass all its method calls to the mother class, who passes it to its i-th player.

    - Except for the handleCollision method: the ALOHA collision avoidance protocol is implemented here.
    """

    def __init__(self, nbPlayers, mother, playerId, nbArms, p0=0.5, alpha_p0=0.5, ftnext=tnext_beta, lower=0., amplitude=1.):
        super(oneALOHA, self).__init__(mother, playerId)
        self.nbPlayers = nbPlayers
        # Parameters for the ALOHA protocol
        assert 0 <= p0 <= 1, "Error: parameter 'p0' for a ALOHA player should be in [0, 1]."
        self.p0 = p0  # Should not be modified
        self.p = p0   # Can be modified
        assert 0 < alpha_p0 <= 1, "Error: parameter 'alpha_p0' for a ALOHA player should be in (0, 1]."
        self.alpha_p0 = alpha_p0
        self.ftnext = ftnext
        # Internal memory
        self.tnext = np.ones(nbArms, dtype=int)  # Only store the delta time

    def __str__(self):   # Better to recompute it automatically
        return '#{}<ALOHA, {}, p0: {}, alpha_p0: {}, beta: {}>'.format(self.playerId + 1, self.mother._players[self.playerId], self.p0, self.alpha_p0, self.ftnext.__name__)

    def startGame(self):
        super(oneALOHA, self).startGame()
        self.p = self.p0
        self.tnext.fill(1)
        # FIXME ?

    def getReward(self, arm, reward):
        """ Receive a reward on arm of index 'arm', as described by the ALOHA protocol.

        - If not collision, receive a reward after pulling the arm.
        """
        # print("- A MEGA player receive reward = {} on arm {}, and time t = {}...".format(reward, arm, self.t))  # DEBUG
        self.rewards[arm] += (reward - self.lower) / self.amplitude
        self.pulls[arm] += 1
        self.p = self.p * self.alpha + (1 - self.alpha)  # Update proba p

    def handleCollision(self, arm):
        """ Handle a collision, on arm of index 'arm'.

        - Warning: this method has to be implemented in the collision model, it is NOT implemented in the EvaluatorMultiPlayers.
        - Note: we do not care on which arm the collision occured.
        """
        # print("- A ALOHA player saw a collision on arm {}, and time t = {} ...".format(arm, self.t))  # DEBUG
        # 1. With proba p, persist
        if rn.random() < self.p:
            self.chosenArm = self.chosenArm  # XXX remove after
        # 2. With proba 1 - p, give up
        else:
            # Random time offset until when this arm self.chosenArm is not sampled
            delta_tnext_k = rn.randint(low=0, high=1 + int(self.ftnext(self.t)))
            self.tnext[self.chosenArm] = self.t + delta_tnext_k
            # Reinitialize the proba p
            self.p = self.p0
            # We give up this arm
            self.chosenArm = None

    def choice(self):
        """ Identify the available arms, and use the underlying single-player policy (UCB, Thompson etc) to choose an arm from this sub-set of arms.

        - FIXME the policy has to have a method choiceFromSubSet
        """
        self.t += 1
        if self.chosenArm is not None:  # We can still exploit that arm
            return self.chosenArm
        else:  # We have to chose a new arm
            # Identify available arms
            availableArms = [k for k in range(self.nbArms) if self.tnext[k] <= self.t]
            result = self.mother._choiceFromSubSet(self.playerId, availableArms)
            # print(" - A oneALOHA player {} had to choose an arm among the set of available arms = {}, her choice was : {} ...".format(self, availableArms, result))  # DEBUG
            return result


# --- Class ALOHA

class ALOHA(BaseMPPolicy):
    """ ALOHA: implementation of the multi-player policy from [Concurrent bandits and cognitive radio network, O.Avner & S.Mannor, 2014](https://arxiv.org/abs/1404.5421).
    """

    def __init__(self, nbPlayers, playerAlgo, nbArms, p0=0.5, alpha_p0=0.5, ftnext=tnext_beta, lower=0., amplitude=1., *args, **kwargs):  # Named argument to give them in any order
        """
        - nbPlayers: number of players to create (in self._players).
        - playerAlgo: class to use for every players.
        - nbArms: number of arms, given as first argument to playerAlgo.

        - p0: initial probability p(0); p(t) is the probability of persistance on the chosenArm at time t
        - alpha_p0: scaling in the update for p(t+1) <- alpha_p0 p(t) + (1 - alpha_p0(t))
        - ftnext: general function, default to t -> t^beta, to know from where to sample a random time t_next(k), until when the chosenArm is unavailable. FIXME try with a t -> log(t) instead

        - *args, **kwargs: arguments, named arguments, given to playerAlgo.

        Example:
        >>> nbArms = 17
        >>> NB_PLAYERS = 6
        >>> p0, alpha_p0, tnext = 0.6, 0.5, tnext_beta
        >>> s = ALOHA(NB_PLAYERS, Thompson, nbArms, p0=p0, alpha_p0=alpha_p0, tnext=tnext)
        >>> s = ALOHA(NB_PLAYERS, UCBalpha, nbArms, p0=p0, alpha_p0=alpha_p0, tnext=tnext, alpha=1)

        - To get a list of usable players, use s.childs.
        - Warning: s._players is for internal use ONLY!
        """
        assert nbPlayers > 0, "Error, the parameter 'nbPlayers' for rhoRand class has to be > 0."
        self.nbPlayers = nbPlayers
        # Interal
        self._players = [None] * nbPlayers
        self.childs = [None] * nbPlayers
        for playerId in range(nbPlayers):
            # Initialize internal algorithm (eg. UCB, Thompson etc)
            self._players[playerId] = playerAlgo(nbArms, *args, lower=lower, amplitude=amplitude, **kwargs)
            self.childs[playerId] = oneALOHA(nbPlayers, self, playerId, nbArms, p0=p0, alpha_p0=alpha_p0, ftnext=ftnext, lower=lower, amplitude=amplitude)
        self.nbArms = nbArms
        self.params = '{} x {}'.format(nbPlayers, str(self._players[0]))

    def __str__(self):
        return "ALOHA({})".format(self.params)

    # --- Proxy methods

    def _startGame_one(self, playerId):
        return self._players[playerId].startGame()

    def _getReward_one(self, playerId, arm, reward):
        return self._players[playerId].getReward(arm, reward)

    def _choice_one(self, playerId):
        return self._players[playerId].choice()

    def _choiceFromSubSet_one(self, playerId, availableArms):
        return self._players[playerId].choiceFromSubSet(availableArms)

    def _choiceWithRank(self, playerId, rank):
        raise NotImplementedError("Error: a oneRhoRand player should only use choice() method, not the choiceWithRank() method.")

    def _handleCollision_one(self, playerId, arm):
        raise NotImplementedError("Error: a oneALOHA player should use the internal handleCollision() method, not the proxy one given to mother class.")