#!/usr/bin/env python

#!/usr/bin/env python
# coding=UTF-8

# File:     sensors.py
# Purpose:  Sensor classes
# Author:   Ryan Adams (@ninetimeout)
# Date:     2016-Dec-17

# NOTE: Please add your name to 'Author:' if you work on this file. Thanks!

# Note: all units are SI: meters/s^2, meters/s, and meters. Time is in microseconds (?)
import logging
import numpy as np
from units import Units
from collections import deque, namedtuple

# @see https://scimusing.wordpress.com/2013/10/25/ring-buffers-in-pythonnumpy/
# RDA: modified to work with any dtype
class RingBuffer():
    "A 1D ring buffer using numpy arrays"
    def __init__(self, length, dtype='f'):
        self.data = np.zeros(length, dtype=dtype)
        self.index = 0

    def extend(self, x):
        "adds array x to ring buffer"
        if x.size:
            x_index = (self.index + np.arange(x.size)) % self.data.size
            self.data[x_index] = x
            self.index = x_index[-1] + 1

    def get(self):
        "Returns the first-in-first-out data in the ring buffer"
        idx = (self.index + np.arange(self.data.size)) %self.data.size
        return self.data[idx]

"""
def ringbuff_numpy_test():
    ringlen = 100000
    ringbuff = RingBuffer(ringlen)
    for i in range(40):
        ringbuff.extend(np.zeros(10000, dtype='f')) # write
        ringbuff.get() #read
"""

class Sensor(object):
    def __init__(self, sim, config):
        self.sim = sim
        self.config = config

        # Communications
        self.step_listeners = []

    def add_step_listener(self, listener):
        """ 
        Register a listener that will be called every step. 
        A step listener can be any class that implements the following method:
        - step_callback(self, sensor, times, samples)
        """
        self.step_listeners.append(listener)

    def create_step_samples(self, dt_usec):
        pass  # deferred to subclasses
        
    def get_csv_headers(self):
        pass  # deferred to subclasses (@todo: maybe...)
        
    def get_debug_headers(self):
        pass  # deferred to subclasses
        
        
class PodSensor(Sensor):
    def __init__(self, sim, config):
        """ A sensor for the pod actual values """
        Sensor.__init__(self, sim, config)

        self.name = "pod_actual"

        pod_fields = ['t', 'p', 'v', 'a', 'he_height']
        # Get the force fields 
        for key, force in self.sim.pod.step_forces.iteritems():
            pod_fields.extend([key+"_x", key+"_y", key+"_z"])

        self.data = namedtuple('pod_actual', pod_fields)
        
    def step(self, dt_usec):
        """ Create a list of samples containing a single sample for this step """
        pod = self.sim.pod
        
        # Note: sensors always return a list of namedtuples. In this case, we always only return 1 'sample' per step. 
        data = [self.sim.elapsed_time_usec, pod.position, pod.velocity, pod.acceleration, pod.he_height]
        for force in self.sim.pod.step_forces.values():
            data.extend([force.x, force.y, force.z])

        samples = [self.data(*data)]  # List containing a single named tuple
        
        for step_listener in self.step_listeners:
            step_listener.step_callback(self, samples)
        

class PollingSensor(Sensor):
    """ Sensor that provides a data stream  """
    
    """
    Note: Sensors will need inputs from the outside world -- sensors will need to 'sample' the world. 
          - Q: How do we connect a sensor to what it needs to measure? 
            A: This is done in the get_step_samples() method by directly accesing self.sim
          - Q: What about recording the 'time' (lerp'd) for each sample? 
            A: ...
          - Probably want an id as well for logging purposes -- put that in config? Insert into config during setup (using the name of the sensor?)
    """

    def __init__(self, sim, config):
        Sensor.__init__(self, sim, config)

        self.logger = logging.getLogger("PollingSensor")

        # Configuration

        # Grab the fixed timestep from the sim. If we wanted to use a variable timestep we would need to do the next calculations in the lerp function
        self.sampling_rate = Units.SI(self.config.sampling_rate)  # Hz

        # @see self._add_noise() and numpy.random.normal
        self.noise_center = self.config.noise.center or 0.0
        self.noise_scale = self.config.noise.scale or 0.0

        # Volatile
        #self.buffer = RingBuffer(config.buffer_size, config.dtype)   # @todo: How to specify dtype in configuration? There should be a string rep of dtype I think 
        self.buffer = None     # Note: we depend on our listeners to handle any buffering/saving/sending of sensor values. Buffer is cleard after each step.
        self.sample_times = None
        self.next_start = 0.0
        self.step_lerp_pcts = None  # Set during step

    
    def create_step_samples(self):
        """ Get the step samples """
        pass  # Deferred to subclasses

        """ Example using pod height:
        start_value = self.sim.pod.last_height
        end_value = self.sim.pod.height

        # Lerp values to get samples
        samples = start_value + self.step_lerp_pcts * (end_value - start_value)  # Or use self.lerp(start_value, end_value), but doing it directly is faster since no function call
        if self.noise_scale > 0:
            # Add gaussian noise if specified
            return samples + np.random.normal(0.0, noise_scale, len(samples))
        else:
            # No noise
            return samples          
        """
    
    def step(self, dt_usec):
        """ Step the sensor and put the results of create_step_samples() into the buffer """

        # If we have no listeners, don't waste time calculating samples
        # @todo: Maybe calculate self.next_step so that we can add sensors during sim, but only if it turns out to be necessary
        if len(self.step_listeners) == 0:
            return
        
        # If the start of our next sample is greater than 1 (step), skip creating samples for this step
        if self.next_start >= 1.0:
            self.next_start -= 1
            return
                
        samples_per_step = self.sampling_rate * dt_usec / 1000000.
        sample_pct_of_step = 1.0/samples_per_step + 0.00000001  # For lerping -- add a tiny amount to eliminate floating point errors (doesn't affect the sim at this scale)

        self.step_lerp_pcts = np.arange(self.next_start, 1.0, sample_pct_of_step)

        # Call get_step_samples() (implemented in subclasses) to get the samples and add them to the buffer
        samples = self.create_step_samples(dt_usec)  # Format np.array([<sample time>, <sample data 1>, ...])

        # Send our data to any attached listeners
        #self.logger.debug("Sending samples to {} step listeners".format(len(self.step_listeners)))
        for step_listener in self.step_listeners:
            step_listener.step_callback(self, samples)

        # Update or start pct for the next step
        # @TODO: If we don't add .0000001 (or any tiny number, really) here the number of samples taken will be off by quite a bit at smaller step sizes. Probably floating point error....
        #self.next_start = sample_pct_of_step - (1 - self.step_lerp_pcts[-1]) +.0000001  # Works, but moved this to sample_pct_of_step calculation
        self.next_start = sample_pct_of_step - (1 - self.step_lerp_pcts[-1])
        
    
    # Helper methods
        
    def _lerp(self, start_value, end_value):
        """ Lerp between the two values using the self.step_lerp_pcts vector and return a vector of lerp'd values """
        return (1.0-self.step_lerp_pcts)*start_value + self.step_lerp_pcts*end_value
        
    def _get_gaussian_noise(self, samples, noise_center=0.0, noise_scale=0.1):
        if noise_scale > 0:
            return np.random.normal(noise_center, noise_scale, len(samples))
        else:
            return 0
    
    def _get_sample_times(self, dt_usec):
        start_time = self.sim.elapsed_time_usec  # Note: this is updated last in Sim.step()
        return self._lerp(start_time, start_time + dt_usec).astype(int)  # as ints because microseconds


class InterruptingSensor(Sensor):

    def __init__(self, sim, config):
        super(InterruptingSensor, self).__init__(sim, config)

    def step(self, dt_usec):
        """ Step the sensor and put the results of create_step_samples() into the buffer """

        # If we have no listeners, don't waste time calculating samples
        # @todo: Maybe calculate self.next_step so that we can add sensors during sim, but only if it turns out to be necessary
        if len(self.step_listeners) == 0:
            return
                        
        # Call get_step_samples() (implemented in subclasses) to get the samples and add them to the buffer
        samples = self.create_step_samples(dt_usec)  # Note: samples for interrupting sensors include the time as the first column

        # Send our data to any attached listeners
        #self.logger.debug("Sending samples to {} step listeners".format(len(self.step_listeners)))
        for step_listener in self.step_listeners:
            step_listener.step_callback(self, samples)


class SensorConsoleWriter():
    """ A sensor step listener that writes to the console """
    def __init__(self, config=None):
        self.config = config  # @todo: define config for this, if needed (e.g. format, etc.)
                
    def step_callback(self, sensor, step_samples):
        # Write values to the console
        for sample in step_samples:
            print ",".join(sample)
            
import csv
class SensorCsvWriter(object):
    def __init__(self, config):
        self.config = config
        self.enabled = False
        
    def play(self):
        self.enabled = True
        
    def pause(self):
        self.enabled = False

    def step_callback(self, sensor, step_samples):
        # This opens the file every time??
        if self.enabled:
            with open(self.config.filename, 'a') as f:
                w = csv.writer(f)
                for sample in step_samples:
                    w.writerow(list(sample))  # Note: each sample is assumed to be a namedtuple of some sort
                
        

class CompoundSensorListener(object):
    """ A listener object that just calls other listeners """

    def __init__(self, config=None):
        self.config = config
        self.step_listeners = []
        
    def step_callback(self, sensor, samples):
        for listener in self.step_listeners:
            listener.step_callback(sensor, samples)
    
    def add_step_listener(self, listener):
        self.step_listeners.append(listener)

# ---------------------------
# Just notes/sketches below here        

class SensorStepListener:
    """ Listens to a sensor -- called after each step with the samples produced during that step. """
    def __init__(self, config):
        self.config = config   # Config can hold a file to log to, logger settings, or whatever you want

    def step_callback(self, sensor, times, samples):
        # @todo: do something with the samples from this step
        pass # Defer to subclasses

    def step(self, dt_usec):
        # @todo: do we need this? Where would it be called? What would it do? 
        pass  # Defer to subclasses
        # If we need to do anything on step. @todo: Where is this called? 


# Sketch of a pin state change listener that fires interrupts
class PinChangeListener(SensorStepListener):
    def __init__(self, config):
        SensorStepListener.__init__(self, config)

        self.pin_state = False
        
    def step_callback(self, sensor, times, samples):
        # Check to see if we changed state and call the interrupt if so. @todo: maybe schedule interrupts? 
        # Note: may want to use a sample listener on this to emulate interrupts so they can be called during the sensor step
        # Note: 
        for sample in samples:
            # Q: What would the pin value be? 1 or 0? a float? 
            if bool(sample) != self.pin_state:
                self.pin_state = bool(sample)
                self.call_isr_or_something(self.pin_state)
        
    def call_isr_or_something(self, pin_state):
        pass  # do something here
        

        
class DataCollector:
    
    def __init__(self, sim, config):
        self.sim = sim
        self.config = config
    
    def step(self, dt_usec):
        pass  # Defer this to subclasses?
        """
        Might look like: 
        - value0 = self.last_height
        - value1 = self.height
        - samples = self.sensor.create_step_samples(value0, value1)
        - self.writers.write(samples.asbin())
        """
        

    


class SensorBuffer:
    """ Collects sensor values and manages their storage/filtering/redirecting? """

    def __init__(self, sim, config):
        pass



import random

class LaserDistanceSensor():
    
    def create_sample(self):
        # @todo: fix this up
        return 18.3 + random.random() * 0.01
                
        
class Accelerometer:
    
    def __init__(self, pod):
        self.pod = pod

        # Volatile
        self.fifo = deque()
        self.sample_overflow = 0.  # Our timestep won't always yield a clean number (e.g. 'we should take 8.6 samples for this dt_usec'. Store the remainder here.)
        
        # Configuration
        self.sampling_rate_hz = 800
        self.buffer_size = 32
        self.precision = 14  # 14 bits
        self.buffer_mode = "something"   # Circular? 
    
    def step(self, dt_usec):
        # Add samples to the buffer based on how much time has passed and our sampling rate
        n_samples = self.sample_overflow + self.sampling_rate_hz * dt_usec / 1000000.0
        self.sample_overflow = n_samples - int(n_samples)  # Save off the remainder
        n_samples = int(n_samples)  # Discard the remainder
        
        for i in xrange(n_samples):
            self.fifo.pushleft(self.create_sample())
        
    def create_sample(self):
        pass
        # sample = self.pod.acceleration + fuzzing?
        # return (x, y, z)
    
class AccelData:
    def __init__(self):
        """
        # @see eng-software-pod/FIRMWARE/PROJECT_CODE/LCCM655__RLOOP__FCU_CORE/ACCELEROMETERS/fcu__accel__ethernet.c
        //fault flags
        vNUMERICAL_CONVERT__Array_U32(pu8Buffer, u32MMA8451__Get_FaultFlags(u8Device));
        pu8Buffer += 4U;

        //X Raw
        vNUMERICAL_CONVERT__Array_S16(pu8Buffer, s16MMA8451_FILTERING__Get_Average(u8Device, AXIS_X));
        pu8Buffer += 2U;

        //Y Raw
        vNUMERICAL_CONVERT__Array_S16(pu8Buffer, s16MMA8451_FILTERING__Get_Average(u8Device, AXIS_Y));
        pu8Buffer += 2U;

        //Z Raw
        vNUMERICAL_CONVERT__Array_S16(pu8Buffer, s16MMA8451_FILTERING__Get_Average(u8Device, AXIS_Z));
        pu8Buffer += 2U;

        //X Accel
        vNUMERICAL_CONVERT__Array_F32(pu8Buffer, f32MMA8451_MATH__Get_GForce(u8Device, AXIS_X));
        pu8Buffer += 4U;

        //Y Accel
        vNUMERICAL_CONVERT__Array_F32(pu8Buffer, f32MMA8451_MATH__Get_GForce(u8Device, AXIS_Y));
        pu8Buffer += 4U;

        //Z Accel
        vNUMERICAL_CONVERT__Array_F32(pu8Buffer, f32MMA8451_MATH__Get_GForce(u8Device, AXIS_Z));
        pu8Buffer += 4U;

        //Pitch
        vNUMERICAL_CONVERT__Array_F32(pu8Buffer, f32MMA8451_MATH__Get_PitchAngle(u8Device));
        pu8Buffer += 4U;

        //Roll
        vNUMERICAL_CONVERT__Array_F32(pu8Buffer, f32MMA8451_MATH__Get_RollAngle(u8Device));
        pu8Buffer += 4U;
        
        """


        self.dtype = np.dtype([
                ('fault_flags', np.uint32),
                ('raw_x', np.int16),
                ('raw_y', np.int16),
                ('raw_z', np.int16),
                ('accel_x', np.float32),
                ('accel_y', np.float32),
                ('accel_z', np.float32),                
                ('pitch', np.float32),
                ('roll', np.float32),                
        ])
        
        self._accel_indices = [0, 4, 5, 6]
        
        self.data = np.array([(0, 0.1, 12, 1234, 0.12345678901234, 0.12345678901234, 0.12345678901234, 0.12345678901234, 0.12345678901234)], dtype=self.dtype)
        self.data['fault_flags'] = 0
        self.data['raw_x'] = 0.1
        self.data['raw_y'] = 12
        self.data['raw_z'] = 31929
        self.data['accel_x'] = 0.12345678901234
        self.data['accel_y'] = 0.23456789012345
        self.data['accel_z'] = 0.34567890123456
        self.data['pitch'] = 0.1000
        self.data['roll'] = 0.2000


        #print len(self.data.tostring(order="C"))
                
    def pack_safeudp_full(self):
        return self.data.tostring(order="C")
        
    def pack_safeudp_cal(self):
        print self.data[0]
        
        return self.data[0].tostring()

class AccelData2:
    
    def __init__(self):
        self.dtype = np.dtype('uint32, int16, int16, int16, float32, float32, float32, float32, float32')
        self.data = np.array([(0, 1, 12, 1234, 0.12345678901234, 0.12345678901234, 0.12345678901234, 0.12345678901234, 0.12345678901234)], dtype=self.dtype)
        print np.asmatrix(self.data)


if __name__ == "__main__":

    ad2 = AccelData2()
    exit()
    
    ad = AccelData()
    print len(ad.pack_safeudp_full())
    print len(ad.pack_safeudp_cal())
    print ""
    
    dt_usec = 100002
    sensor = LaserDistanceSensor()
    sensor.sampling_rate_hz = 200
    for i in xrange(10):
        sensor.step(dt_usec)
        print len(sensor.fifo)
    