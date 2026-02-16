# Ed Callaghan
# Simple wrapping of a dict and a mutex
# October 2024

import threading

class ThreadSafeDict(dict):
    def __init__(self, *args, **kwargs):
        super(ThreadSafeDict, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()

    def Assign(self, key, value):
        self.lock.acquire()
        self[key] = value
        self.lock.release()

    def Update(self, rhs):
        self.lock.acquire()
        for key,value in rhs.items():
            self[key] = value
        self.lock.release()

    def AsDict(self):
        self.lock.acquire()
        rv = {k: v for k,v in self.items()}
        self.lock.release()
        return rv
