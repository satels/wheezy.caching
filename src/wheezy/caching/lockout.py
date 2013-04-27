
""" ``lockout`` module.
"""

from warnings import warn

from wheezy.caching.utils import total_seconds


class Locker(object):
    """ Used to define lockout terms.
    """

    def __init__(self, cache, forbid_action, namespace=None,
                 key_prefix='c', **terms):
        self.cache = cache
        self.forbid_action = forbid_action
        self.namespace = namespace
        self.key_prefix = key_prefix
        self.terms = terms

    def define(self, name, **terms):
        """ Defines a new lockout with given `name` and `terms`.
            The `terms` keys must correspond to `known terms` of locker.
        """
        if not terms:  # pragma: nocover
            warn('Locker: no terms', stacklevel=2)
        key_prefix = '%s:%s:' % (self.key_prefix, name.replace(' ', '_'))
        counters = [self.terms[t](**terms[t]) for t in terms]
        return Lockout(name, counters, self.forbid_action,
                       self.cache, self.namespace, key_prefix)


class Counter(object):
    """ A container of various attributes used by lockout.
    """

    def __init__(self, key_func, count, period, duration,
                 reset=True, alert=None):
        self.key_func = key_func
        self.count = count
        self.period = total_seconds(period)
        self.duration = total_seconds(duration)
        self.reset = reset
        self.alert = alert


class Lockout(object):
    """ A lockout is used to enforce terms of use policy.
    """

    def __init__(self, name, counters, forbid_action,
                 cache, namespace, key_prefix):
        self.name = name
        self.counters = counters
        self.cache = cache
        self.namespace = namespace,
        self.key_prefix = key_prefix
        self.forbid_action = forbid_action

    def guard(self, func):
        """ A guard decorator is applied to a `func` which returns a
            boolean indicating success or failure. Each failure is a
            subject to increase counter. The counters that supports
            `reset` are deleted on success.
        """
        def guard_wrapper(ctx, *args, **kwargs):
            succeed = func(ctx, *args, **kwargs)
            if succeed:
                keys = [self.key_prefix + c.key_func(ctx)
                        for c in self.counters if c.reset]
                keys and self.cache.delete_multi(keys, 0, '', self.namespace)
            else:
                for c in self.counters:
                    key = self.key_prefix + c.key_func(ctx)
                    max_try = self.cache.add(
                        key, 1, c.period, self.namespace
                    ) and 1 or self.cache.incr(key, 1, self.namespace)
                    #print("%s ~ %d" % (key, max_try))
                    if max_try >= c.count:
                        self.cache.delete(key, 0, self.namespace)
                        self.cache.add('lock:' + key, 1,
                                       c.duration, self.namespace)
                        c.alert and c.alert(ctx, self.name, c)
            return succeed
        return guard_wrapper

    def forbid_locked(self, func):
        """ A decorator that forbids access (by a call to `forbid_action`)
            to `func` once the counter threshold is reached (lock is set).
        """
        key_prefix = 'lock:' + self.key_prefix

        def forbid_locked_wrapper(ctx, *args, **kwargs):
            locks = self.cache.get_multi(
                [key_prefix + c.key_func(ctx) for c in self.counters],
                '', self.namespace)
            if locks:
                return self.forbid_action(ctx)
            return func(ctx, *args, **kwargs)
        return forbid_locked_wrapper
