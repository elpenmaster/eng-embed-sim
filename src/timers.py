#!/usr/bin/env python

# File:     timers.py
# Purpose:  Provide timers for the timed FCU callbacks
# Author:   Ryan Adams (radams@cyandata.com, @ninetimeout)
# Date:     2017-Jan-16

import time
from datetime import datetime
import threading
import numpy as np

from units import Units

class Timer:
    """ Basic timer with callback and time dialation """

    def __init__(self, interval_sec, callback):
        self.interval = interval_sec
        self.callback = callback


        # Time dialation factor (for adjusting real time to sim time for timers)
        self.dialation = 1.0
        self.delay = self.interval  # Will be adjusted by the set_dialation method
        self.set_dialation(self.dialation)

        self.stop_flag = False

    def set_dialation(self, dialation):
        """ set the time-dialated delay """
        self.dialation = dialation
        self.delay = self.interval * self.dialation

    def start_threaded(self):
        t = threading.Thread(target=self.run, args=())
        t.daemon = True
        t.start()
        return t

    def run(self):
        t0 = time.clock()
        while True:
            if self.stop_flag:  # Break out if we need to
                self.stop_flag = False  # so we can restart
                break
            t1 = time.clock()
            if t1 - t0 >= self.delay:
                self.callback()
                t0 = t1        

    def stop(self):
        self.stop_flag = True
        

class TimeDialator(Timer):
    """ A timer that controls the dialation of time (sim time vs real time) for other timers.
        Note that this can either be run as a timer or stepped directly by the simulation (use either, but not both probably.)
        @todo: Probably split this into two classes: one that can be run as a timer and one that is stepped by the simulator. Stepping will be more accurate. 
    """
    
    def __init__(self, sim, interval_sec=None, timers=None):
        Timer.__init__(self, interval_sec, self.dialate_time)
        self.sim = sim
        
        self.timers = timers or []

        self.last_real_time = None
        self.last_sim_time = None

    def add_timer(self, timer):
        self.timers.append(timer)
    
    def add_timers(self, timers):
        self.timers.extend(timers)
    
    def dialate_time(self, dt_usec=None):
        """ Calculate the time dialation and set it on our timers """
        if self.last_real_time is None:
            # Initialize here so that we can ignore thread startup times and whatnot
            self.last_real_time = time.clock()
            self.last_sim_time = self.sim.elapsed_time_usec * 1000000.0
            return

        real_time_diff = time.clock() - self.last_real_time
        if dt_usec is None:
            # We didn't have one passed in, so calculate it. This is used if we're running as a timer rather than directly stepped. 
            sim_time_diff = (self.sim.elapsed_time_usec / 1000000.0) - self.last_sim_time 
        else:
            sim_time_diff = dt_usec / 1000000.0
            
        # Dialation is the ratio of real time to sim time: 10s real time to 1s sim time = dialation factor of 10. Or 1s real time to 2s sim time = dialation factor of .5
        self.dialation = real_time_diff / sim_time_diff
        for timer in self.timers:
            timer.set_dialation(self.dialation)
        self.logger.debug("Set time dialation to {}".format(self.dialation))
        
        # Update our times
        self.last_real_time = time.clock()
        self.last_sim_time = self.sim.elapsed_time_usec / 1000000.0

    def step(self, dt_usec):
        """ step method so that we can be directly stepped instead of used as a timer """
        self.dialate_time(dt_usec)
        
# @todo: add a TimeAdjustor class that adjust delay (and maybe overhead) for timers that are lagging/speeding


class TimerTest:
    # Test a 10 microsecond timer in python on windows
    
    def __init__(self, n):
        self.n = n
        self.q = []
        self.total_time = 0.0
        self.adjusted_delay = 0.0000005
        
    def run(self):
        start = datetime.now()
        t0 = time.clock()
        for i in xrange(self.n):
            if i == 3:
                start = datetime.now()
            t1 = time.clock()
            if t1 - t0 >= self.adjusted_delay:  # 10 microseconds, minus some amount for processing time
                self.q.append(t1 - t0)
                t0 = t1
        
        self.total_time = datetime.now() - start
        
        print self.results()
        
    def results(self):
        a = []
        #for t in self.q:
        #    a.append("{0:.20f}".format(t))

        a.append("-- Results -----")
        a.append("Timer test completed {} ticks in {}s".format(len(self.q), self.total_time))
        a.append("Average time between calls: {0:.20f} usec".format(np.mean(self.q[3:]) * 1000000))
        
        return "\n".join(a)
        
        
if __name__ == "__main__":
    print "-- Timer Test -----"

    tt = TimerTest(100000)
    tt.run()

