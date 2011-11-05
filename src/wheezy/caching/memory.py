
""" ``memory`` module.
"""

from thread import allocate_lock
from time import time as unixtime


def expires(now, time):
    """
        ``time`` is below 1 month

        >>> expires(10, 1)
        11

        more than month

        >>> expires(10, 3000000)
        3000000

        otherwise

        >>> expires(0, 0)
        0
        >>> expires(0, -1)
        0
    """
    if time > 0:
        if time < 2592000:  # 1 month
            return now + time
        else:
            return time
    else:
        return 0


def find_expired(bucket_items, now):
    """
        If there are no expired items in the bucket returns
        empty list

        >>> bucket_items = [('k1', 1), ('k2', 2), ('k3', 3)]
        >>> find_expired(bucket_items, 0)
        []
        >>> bucket_items
        [('k1', 1), ('k2', 2), ('k3', 3)]

        Expired items are returned in the list and deleted from
        th bucket

        >>> find_expired(bucket_items, 2)
        ['k1']
        >>> bucket_items
        [('k2', 2), ('k3', 3)]
    """
    expired_keys = []
    for i in xrange(len(bucket_items) - 1, -1, -1):
        (key, expires) = bucket_items[i]
        if expires < now:
            expired_keys.append(key)
            del bucket_items[i]
    return expired_keys


class CacheItem(object):
    __slots__ = ['key', 'value', 'expires']

    def __init__(self, key, value, expires):
        self.key = key
        self.value = value
        self.expires = expires


class MemoryCache(object):

    def __init__(self, buckets=60, bucket_interval=15):
        self.period = buckets * bucket_interval
        self.interval = bucket_interval
        self.items = {}
        self.lock = allocate_lock()
        self.expire_buckets = [(allocate_lock(), [])
                for i in xrange(0, buckets)]
        self.last_expire_bucket_id = -1

    def set(self, key, value, time=0):
        """
            Sets a key's value, regardless of previous contents in cache

            >>> c = MemoryCache()
            >>> c.set('k', 'v', 100)
            True
        """
        return self.store(key, value, time, 0)

    def set_multi(self, mapping, time=0, key_prefix=''):
        """
            >>> c = MemoryCache()
            >>> c.set_multi({'k1': 1, 'k2': 2}, 100)
            []
        """
        return self.store_multi(mapping, time, key_prefix)

    def add(self, key, value, time=0):
        """
            Sets a key's value, if and only if the item is not already

            >>> c = MemoryCache()
            >>> c.add('k', 'v', 100)
            True
            >>> c.add('k', 'v', 100)
            False
        """
        return self.store(key, value, time, 1)

    def add_multi(self, mapping, time=0, key_prefix=''):
        """
            >>> c = MemoryCache()
            >>> c.add_multi({'k': 'v'}, 100)
            []
            >>> c.add_multi({'k': 'v'}, 100)
            ['k']
        """
        return self.store_multi(mapping, time, key_prefix, 1)

    def replace(self, key, value, time=0):
        """
            Replaces a key's value, failing if item isn't already

            >>> c = MemoryCache()
            >>> c.replace('k', 'v', 100)
            False
            >>> c.add('k', 'v', 100)
            True
            >>> c.replace('k', 'v', 100)
            True
        """
        return self.store(key, value, time, 2)

    def replace_multi(self, mapping, time=0, key_prefix=''):
        """
            >>> c = MemoryCache()
            >>> c.replace_multi({'k': 'v'}, 100)
            ['k']
            >>> c.add_multi({'k': 'v'}, 100)
            []
            >>> c.replace_multi({'k': 'v'}, 100)
            []
        """
        return self.store_multi(mapping, time, key_prefix, 2)

    def get(self, key, namespace=None):
        """
            Looks up a single key.

            If ``key`` is not found return None

            >>> c = MemoryCache()
            >>> c.get('k')

            Otherwise return value

            >>> c.set('k', 'v', 100)
            True
            >>> c.get('k')
            'v'
            >>> from timeit import timeit
            >>> #timeit(lambda: c.get('k'))

            There is item in cached that expired

            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.get('k')
        """
        now = int(unixtime())
        items = self.items
        self.lock.acquire(1)
        try:
            entry = items[key]
            if entry.expires < now:
                del items[key]
                return None
            return entry.value
        except KeyError:
            return None
        finally:
            self.lock.release()

    def get_multi(self, keys, key_prefix=''):
        """

            >>> c = MemoryCache()
            >>> c.get_multi(('k1', 'k2', 'k3'))
            {}
            >>> c.store('k1', 'v1', 100)
            True
            >>> c.store('k2', 'v2', 100)
            True
            >>> c.get_multi(('k1', 'k2'))
            {'k2': 'v2', 'k1': 'v1'}

            >>> from timeit import timeit
            >>> #timeit(lambda: c.get_multi(('k1', 'k2')))

            There is item in cache that expired

            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.get_multi(('k', ))
            {}
        """
        now = int(unixtime())
        results = {}
        items = self.items
        self.lock.acquire(1)
        try:
            for k in keys:
                key = key_prefix + k
                try:
                    entry = items[key]
                    if entry.expires < now:
                        del items[key]
                    else:
                        results[k] = entry.value
                except KeyError:
                    pass
        finally:
            self.lock.release()
        return results

    def delete(self, key, seconds=0):
        """
            Deletes a key from cache.

            If ``key`` is not found return False

            >>> c = MemoryCache()
            >>> c.delete('k')
            False
            >>> c.store('k', 'v', 100)
            True
            >>> c.delete('k')
            True

            There is item in cache that expired

            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.delete('k')
            False
        """
        now = int(unixtime())
        items = self.items
        self.lock.acquire(1)
        try:
            entry = items[key]
            del items[key]
            if entry.expires < now:
                return False
            return True
        except KeyError:
            return False
        finally:
            self.lock.release()

    def delete_multi(self, keys, seconds=0, key_prefix=''):
        """

            >>> c = MemoryCache()
            >>> c.delete_multi(('k1', 'k2', 'k3'))
            True
            >>> c.store_multi({'k1':1, 'k2': 2}, 100)
            []
            >>> c.delete_multi(('k1', 'k2'))
            True

            There is item in cached that expired

            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.get_multi(('k', ))
            {}
        """
        items = self.items
        self.lock.acquire(1)
        try:
            for key in keys:
                try:
                    del items[key_prefix + key]
                except KeyError:
                    pass
        finally:
            self.lock.release()
        return True

    def store(self, key, value, time=0, op=0):
        """
            There is item in cached that expired

            >>> c = MemoryCache()
            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.store('k', 'v', 100)
            True

            There is item in expire_buckets that expired

            >>> c = MemoryCache()
            >>> i = ((int(unixtime()) % c.period)
            ...         / c.interval) - 1
            >>> c.expire_buckets[i] = (allocate_lock(), [('x', 10)])
            >>> c.store('k', 'v', 100)
            True
        """
        now = int(unixtime())
        time = expires(now, time)
        items = self.items
        self.lock.acquire(1)
        try:
            try:
                entry = items[key]
                if entry.expires < now:
                    del items[key]
                elif op == 1:  # add
                    return False
            except KeyError:
                if op == 2:  # replace
                    return False
            items[key] = CacheItem(key, value, time)
        finally:
            self.lock.release()
        if time > 0:
            expired_keys = None
            bucket_id = (now % self.period) / self.interval
            bucket_lock, bucket_items = self.expire_buckets[bucket_id - 1]
            bucket_lock.acquire(1)
            try:
                if self.last_expire_bucket_id != bucket_id:
                    self.last_expire_bucket_id = bucket_id
                    expired_keys = find_expired(bucket_items, now)
                bucket_items.append((key, time))
            finally:
                bucket_lock.release()
            if expired_keys:
                self.delete_multi(expired_keys)
        return True

    def store_multi(self, mapping, time=0, key_prefix='', op=0):
        """
            There is item in cached that expired

            >>> c = MemoryCache()
            >>> c.items['k'] = CacheItem('k', 'v', 1)
            >>> c.store_multi({'k': 'v'}, 100)
            []

            There is item in expire_buckets that expired

            >>> c = MemoryCache()
            >>> i = ((int(unixtime()) % c.period)
            ...         / c.interval) - 1
            >>> c.expire_buckets[i] = (allocate_lock(), [('x', 10)])
            >>> c.store_multi({'k': 'v'}, 100)
            []
        """
        now = int(unixtime())
        time = expires(now, time)
        items = self.items
        keys_failed = []
        succeeded = []
        self.lock.acquire(1)
        try:
            for k, value in mapping.iteritems():
                key = key_prefix + k
                try:
                    entry = items[key]
                    if entry.expires < now:
                        del items[key]
                    elif op == 1:  # add
                        keys_failed.append(k)
                        continue
                except KeyError:
                    if op == 2:  # replace
                        keys_failed.append(k)
                        continue
                items[key] = CacheItem(key, value, time)
                succeeded.append((key, time))
        finally:
            self.lock.release()
        if time > 0 and succeeded:
            expired_keys = None
            bucket_id = (now % self.period) / self.interval
            bucket_lock, bucket_items = self.expire_buckets[bucket_id - 1]
            bucket_lock.acquire(1)
            try:
                if self.last_expire_bucket_id != bucket_id:
                    self.last_expire_bucket_id = bucket_id
                    expired_keys = find_expired(bucket_items, now)
                bucket_items.extend(succeeded)
            finally:
                bucket_lock.release()
            if expired_keys:
                self.delete_multi(expired_keys)
        return keys_failed

    def flush_all(self):
        """
            >>> c = MemoryCache()
            >>> c.set_multi({'k1': 1, 'k2': 2}, 100)
            []
            >>> c.flush_all()
            True
        """
        self.lock.acquire(1)
        try:
            self.items.clear()
            for bucket_lock, bucket_items in self.expire_buckets:
                bucket_lock.acquire(1)
                try:
                    del bucket_items[:]
                finally:
                    bucket_lock.release()
        finally:
            self.lock.release()
        return True


if __name__ == '__main__':  # pragma: nocover
    import doctest
    doctest.testmod()
