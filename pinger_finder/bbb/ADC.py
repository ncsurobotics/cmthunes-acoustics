from __future__ import print_function

import time
import mmap
import struct
import logging
from os import path

import platform
if 'Linux-3.8.13-bone47-armv7l-with-debian' in platform.platform():
    import pypruss  # Python PRUSS wrapper
elif 'Linux-4.1.38-bone-rt-r24-armv7l-with-debian-8.7' in platform.platform():
    import pypruss  # Python PRUSS wrapper
elif '-bone-' in platform.platform():
    import pypruss  # Python PRUSS wrapper
else:
    print("ADC: Detected that this code is not running on a BBB device. Pypruss is unavailable")

import numpy as np

from . import boot
from . import BIN_DIR
from .port import Port

logging.basicConfig(level=logging.WARNING, format='%(module)s.py: %(asctime)s - %(levelname)s - %(message)s')

# Global ADC program Constants
PRU0_DDR_MEM_OFFSET = 1
PRU0_SL_MEM_OFFSET = 2
PRU0_CR_Mem_Offset = 3
PRU0_DB_MEM_OFFSET = 4
PRU0_THR_Mem_Offset = 5
HC_CR = 0xBEBC200
F_CLK = 200e6

INIT0 = path.join(BIN_DIR, "init0.bin")
INIT1 = path.join(BIN_DIR, "init1.bin")
ADS7865_MasterPRU = path.join(BIN_DIR, "ADS7865_sample.bin")
ADS7865_ClkAndSamplePRU = path.join(BIN_DIR, "pru1.bin")

WORD_SIZE = 12

BYTES_PER_SAMPLE = 4
MIN_SAMPLE_LENGTH = 2
DEFAULT_DAC_VOLTAGE = 2.49612  # volts
DEFAULT_THRESHOLD = 0  # volts
TOTAL_CHANNELS = 4
SAMPLES_PER_CONV = 2
STATUS_BLOCK = 1
TIMEOUT_STATUS_BIT = 2
DBOVF_BIT = 3
TFLG0_BIT = 4
TFLG1_BIT = 5

CONV_RATE_LIMIT = 800e3  # Hertz

PLUSMINUS = u'\xb1'.encode('utf-8')
DIFF_PAIR_1 = "CHA0" + PLUSMINUS
DIFF_PAIR_2 = "CHA1" + PLUSMINUS
DIFF_PAIR_3 = "CHB0" + PLUSMINUS
DIFF_PAIR_4 = "CHB1" + PLUSMINUS

CODE_READDAC = 0x103
CODE_SWRESET = 0x105
CODE_READSEQ = 0x106
CODE_WRITEDAC = 0x101

# Global Functions


def read_sample(user_mem, sample_length):
    """
    Args:
        user_mem:
        sample_length:
    """

    with open("/dev/mem", "r+b") as f:  # Open the physical memory device
        ddr_mem = mmap.mmap(f.fileno(), user_mem['filelen'], offset=user_mem['offset'])  # mmap the right area

    y = []
    for i in range(sample_length):
        a = user_mem['start'] + i * 4
        b = a + 4
        c = struct.unpack("L", ddr_mem[a:b])[0]  # Parse the data
        y.append(c)
        # print(c)

    ddr_mem.close()
    f.close()
    return y


def twos_comp(val, bits):
    """ Compute the 2's compliment of int value val, of n bits """
    if (val & (1 << (bits - 1))) != 0:
        val -= (1 << bits)

    return val


def get_bit(word, bit):
    """Check if "bit" is set in "word". Word can be of any arbitrary
    length."""
    return ((word & (1 << bit)) != 0)


def conv_rate_warning():
    logging.warning("Your code updates the conversion rate instead of the"
                    + " sample rate at the end user level. This goes against the"
                    + " design spec, and you should fix it such that your code"
                    + " accepts sample rates at the user level")

###################################
######    ADS7865 Class ###########
###################################
###################################

DB_pin_table = ['P9_26', 'P8_46', 'P8_45', 'P8_44', 'P8_43', 'P8_42', 'P8_41', 'P8_40', 'P8_39', 'P8_29', 'P8_28', 'P8_27']
WR_pin = 'P9_31'
BUSY_pin = 'P9_27'
CS_pin = 'P9_25'
RD_pin = 'P9_30'
CONVST_pin = 'P9_29'


class ADS7865():

    """ Allows the user to instantiate an object representing the system
    ADS7865, an analog to digital converter IC by Texas Instruments.
    Incorporates attributes relating to ADC's config, and functions
    for changing the config as well as functions for collecting strings of
    samples in realtime
    """

    def __init__(self, sr=0.0, smp_len=0):
        """ Configures several BBB pins as necessary to hold the ADC in an idle state

        Args:
            cr: Conversion Rate (float)
            smp_len: Sample Length (integer)


        Parameters (in order of initialization):
            self.DBus
            self.WR
            self._RD
            self._CONVST
            self._CS
            self."ddr stuff"
            self.n_channels
            self.conversion_rate
            self.deadband_ms
            self.arm_status
            self.seq_desc
            self.ch
            self.delay
            self.digital_gain
            self.threshold
            self.corrected_threshold
            self.cr_specd
            self.modified
            self.sample_rate
            self.dac_voltage
            self.LSB
            self.TOF
            self.TRG_CH
            self.digital_gain
        """
        # Loads the BBB cape overlays that allow control of the PRUSS
        # and it's IO via pypruss. Note: pypruss will not work correctly
        # until this system level command is ran. Do not try to use the
        # pypruss library before running this command.
        boot.load()

        # GPIO Stuff
        self.DBus = Port(DB_pin_table)
        self.DBus.set_port_dir("in")

        self.WR = Port(WR_pin)
        self.WR.set_port_dir("out")
        self.WR.write_to_port(1)

        self._RD = Port(RD_pin)
        self._RD.set_port_dir("out")
        self._RD.write_to_port(1)

        self._CONVST = Port(CONVST_pin)
        self._CONVST.set_port_dir("out")
        self._CONVST.write_to_port(1)

        self._CS = Port(CS_pin)
        self._CS.set_port_dir("out")
        self._CS.write_to_port(0)

        # PRUSS Stuff
        self.ddr = {}
        self.ddr['addr'] = pypruss.ddr_addr()
        self.ddr['size'] = pypruss.ddr_size()
        self.ddr['start'] = 0x10000000
        self.ddr['filelen'] = self.ddr['size'] + 0x10000000
        self.ddr['offset'] = self.ddr['addr'] - 0x10000000
        self.ddr['end'] = 0x10000000 + self.ddr['size']

        msg = ("ADS7865: Allowing one 32bit memory block per sample, it is "
               "possible to collect {samp:.1f}K Samples in a single burst. These "
               "sample points are stored in DDRAM, which is found at the "
               "address range starting at {addr}")

        logging.info(msg.format(
            samp=self.ddr['size'] / 1000.0,
            addr=str(hex(self.ddr['addr'])))
        )

        self.sampling_rate = sr
        self.deadband_ms = 0
        self.sample_length = int(smp_len)
        self.arm_status = "unknown"
        self.seq_desc = "unknown"
        self.ch = ['unknown'] * 4
        self.delay = [-99] * 4

        self.digital_gain = 1

        self.update_threshold(DEFAULT_THRESHOLD)
        self.sr_specd = 0  # parameter for keeping the up with the last spec
        self.modified = True
        self.sample_rate = None
        self.dac_voltage = DEFAULT_DAC_VOLTAGE
        self.lsb = self.dac_voltage / (2**(WORD_SIZE - 1))  # Volts

        # Loads overlays: For that will be later needed for
        # muxing pins from GPIO to pruout/pruin types and vice versa.
        self.sw_reset()

        # Any other variables that will later be relevent
        self.TOF = None
        self.TRG_CH = None
        self.y = None
        

    ############################
    #### GPIO Commands  #######
    ############################
    def config(self, cmd_list):
        """ Takes a list of hex values (cmd_list) and bitbangs the ADC
        accordingly. User may refer to the datasheet for an explanation
        of what the hex values actually mean. For examples of correct
        application, see: ez_config() method
        """

        # Callee save the port direction
        #callee_sPD = self.DBus.portDirection

        #
        if (boot.arm_state() == True):
            logging.warning('ADC is armed! And thus, it cannot be issued any commands! ' +
                'program will go ahead and dearm ADC immediately, but take note ' +
                'that the action of dearming the ADC takes about 1000ms, and ' +
                'this delay may severly hinder the performance of your autonomous ' +
                'code if you weren\'t expecting this to happen. The better ' +
                'practice is to dearm the adc yourself.')
            self.unready()
        
        if (boot.arm_state() == None):
            logging.warning('ADC is neither armed nor unarmed. It is in ' +
                'a modified state. This usually happens when the bbb ' +
                'is first booted or the user modified the pin configuration ' +
                '(config-pin) in a non-conventional way. Action will be ' +
                'taken to "dearm" the adc now, but if this is not ' +
                'expected behavior, please investigate this issue.')
            self.unready()
                
            
            
        for cmd in cmd_list:
            self.WR.write_to_port(0)  # Open ADC's input Latch

            self.DBus.set_port_dir("out")  # Latch open, safe to make DB pins an out
            self.DBus.write_to_port(cmd)  # Write the value to the DB pins

            logging.info('ADS7865: Databus cmd %s has been sent.' % self.DBus.read_str())
            self.WR.write_to_port(1)  # Latch down the input

        self.DBus.set_port_dir("in")  # Return DB pins back to inputs.

    def ez_config(self, sel=None):
        """ Allows the user to access commonly used config command (presets).

        Args:
            sel: An integer from 0 to 5 representing a particular preset
        """

        # NOTES TO USER
        # --At powerup, sequencer_register=0x000
        # --Capturing one channel (non-pair) in isolation is doable by selecting sel=0
        # or sel=1 (since ADS7865 resets the data_output pointer at the beginning of every
        # CONVST), but the user must also take the extra precaution to disable the
        # "sub-sampling" portion of the PRUSS code in order for it to work.

        if sel is None:
            # Generate Query to user to see what kind of config he wants
            options = ["0a/0b differential channel pair",
                       "1a/1b differential channel pair",
                       "0a/0b differential channel pair w/ sequencer re-init",
                       "1a/1b differential channel pair w/ sequencer re-init",
                       "0a/0b -> 1a/1b in FIFO style",
                       "1a/1b -> 0a/0b in FIFO style"]

            print("Please select from one of the options below:")
            for i in range(len(options)):
                print("  %d: %s" % (i, options[i]))

            # Take input
            sel = eval(raw_input("Enter number here: "))

        # Single channel (pair) enable
        if sel == 0:
            # User has chosen to sample the 0a/0b differential channel pair.
            self.config([0x100])

            # Update statuses
            seq = "CHA0" + PLUSMINUS + "/CHB0" + PLUSMINUS
            chans = [DIFF_PAIR_1, DIFF_PAIR_3, '', '']
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 2

        elif sel == 1:
            # User has chosen to sample the 1a/1b differential channel pair.
            self.config([0xD00])

            # Update statuses
            seq = "CHA1" + PLUSMINUS + "/CHB1" + PLUSMINUS
            chans = [DIFF_PAIR_2, DIFF_PAIR_4, '', '']
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 2

        # Single channel (pair) enable with sequencer reinitialization
        elif sel == 2:
            # User has chosen to sample the 0a/0b differential channel pair
            # while disabling the sequencer register. NOTE: The reason why
            # this would ever be necessary is unclear, as it seems to have
            # the same functionality of ez_config 0.
            self.config([0x104, 0x000])

            # Update statuses
            seq = "CHA0" + PLUSMINUS + "/CHB0" + PLUSMINUS
            chans = [DIFF_PAIR_1, DIFF_PAIR_3, '', '']
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 2

        elif sel == 3:
            # User has chosen to sample the 1a/1b differential channel pair
            # while disabling the sequencer register NOTE: The reason why
            # this would ever be necessary is unclear, as it seems to have
            # the same functionality of ez_config 1.
            self.config([0x304, 0x000])

            # Update statuses
            seq = "CHA1" + PLUSMINUS + "/CHB1" + PLUSMINUS
            chans = [DIFF_PAIR_2, DIFF_PAIR_4, '', '']
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 2

        # Dual channel (pair) enable
        elif sel == 4:
            # User has chosen to sample the 0a/0b -> 1a/1b in FIFO style
            self.config([0x104, 0x230])

            # Update statuses
            seq1 = "CHA0" + PLUSMINUS + "/CHB0" + PLUSMINUS
            seq2 = "CHA0" + PLUSMINUS + "/CHB0" + PLUSMINUS
            seq = seq1 + " -> " + seq2
            chans = [DIFF_PAIR_1, DIFF_PAIR_3, DIFF_PAIR_2, DIFF_PAIR_4]
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 4

        elif sel == 5:
            # User has chosen to sample the 1a/1b -> 0a/0b in FIFO style
            self.config([0x104, 0x2c0])

            # Update statuses
            seq1 = "CHA1" + PLUSMINUS + "/CHB1" + PLUSMINUS
            seq2 = "CHA1" + PLUSMINUS + "/CHB1" + PLUSMINUS
            seq = seq1 + " -> " + seq2
            chans = [DIFF_PAIR_2, DIFF_PAIR_4, DIFF_PAIR_1, DIFF_PAIR_3]
            self.update_config_text(seq, chans)

            # Update n channels
            self.n_channels = 4

        if self.sr_specd:       # Last parameter that the user specd was SR
            self.update_sample_rate(self.sample_rate)
        else:
            conv_rate_warning()

    def update_delays(self):
        if self.n_channels == 2:
            self.delay = [0, 0]
        elif self.n_channels == 4:
            if self.conversion_rate != 0:
                delay = 1 / self.conversion_rate
            else:
                delay = None

            self.delay = [0, 0, delay, delay]
        else:
            raise IOError("%r is not a valid channel size." % self.n_channels)

    def preset(self, sel):
        """
        """

        if sel == 0:
            """Primary competition config. This is the goto place for
            determining the samplesize, sampling rate, # of simultaneous
            channels, and (initial) threshold value.
            """
            self.update_deadband_ms(0.5e3)
            self.set_sample_len(1e3)
            self.update_sample_rate(300e3)
            self.update_threshold(1)
            self.ez_config(5)
            
        elif sel == 1:
            """Secondary competition config. This is the goto place for
            determining the samplesize, sampling rate, # of simultaneous
            channels, and (initial) threshold value.
            """
            self.update_deadband_ms(1)
            self.set_sample_len(1e3)
            self.update_sample_rate(800e3)
            self.update_threshold(.1)
            self.ez_config(0)

        elif sel == 100:
            """
            Prototype (Test config #0)
            Date: Friday, May 8th

            Purpose: Anything

            General Considerations: This isn't as much a preset as much as
            it is a prototyping tool. Unlike other presets embedded in this
            function, the user is free to change the settings anytime as he
            sees fit. If something more "stable" is desirable, try another
            preset or make a new one."""
            self.update_deadband_ms(0)
            self.set_sample_len(1e3)
            self.update_sample_rate(300e3)
            self.update_threshold(.1)
            self.ez_config(0)
            
        elif sel == 101:
            """
            Test Config for Acoustics terminal
            Date: Wednesday, May 13

            Purpose: Faciliting tests on acoustics_terminal.py.

            General Considerations: Changes to this config are okay
            as long as they're for acoustics_terminal.py.
            """
            self.update_deadband_ms(0)
            self.set_sample_len(1e3)
            self.update_sample_rate(300e3)
            self.update_threshold(1)
            self.ez_config(4)

        elif sel == 102:
            """
            Test Config for echo measurements
            Date: June 16, 2015

            Purpose: Long recording for watching all signals over a
            long span of time in the acoustics_terminal app.
            """
            self.update_deadband_ms(1)
            self.set_sample_len(10e3)
            self.update_sample_rate(400e3)
            self.update_threshold(.5)
            self.ez_config(4)

        else:
            logging.warning("Unknown preset!")

    def read_sequence(self):
        """
        """

        # Send cmd telling ADC to output it's SEQ config
        self.config([CODE_READSEQ])

        # Read ADC's databus
        self._RD.write_to_port(0)
        seq = self.DBus.read_str()
        self._RD.write_to_port(1)

        # print config to the user
        print("config of sequencer: %s" % seq)

    def read_dac(self):
        """ Read from digital-analog converter
        """

        # Send cmd telling ADC to output it's SEQ config
        self.config([CODE_READDAC])

        # Read ADC's databus
        self._RD.write_to_port(0)
        dac_s = self.DBus.read_str()
        self._RD.write_to_port(1)

        # print config to the user
        print("config of DAC: %s" % dac_s)

        # interpret value
        dac_voltage_readout = self.dac_str_to_voltage(dac_s)
        print("... Vdac = %.5f volts" % dac_voltage_readout)

        # Update DAC related atributes
        self.dac_voltage = dac_voltage_readout
        self.lsb = self.dac_voltage / (2**(WORD_SIZE - 1))  # Volts

    def write_dac(self, val):
        self.config([0x101])
        self.config([val])
        self.read_dac()

    def _update_conversion_rate(self, cr):
        """ Update the conversion rate

        Args:
            cr: conversion rate
        """

        # Update modified bit
        self.modified = True

        # Update Conversioning bit
        self.conversion_rate = float(cr)
        self.sample_rate = self.cr_to_sr(cr)

        if cr > CONV_RATE_LIMIT:
            logging.warning("Your spec'd conversion rate"
                            + " exceeds the system's spec (%dKHz)" % CONV_RATE_LIMIT / 1000)

        self.sr_specd = False

    def update_sample_rate(self, sr):
        """ Update the sample rate

        Args:
            sr: Sample rate
        """
        # Update modified bit
        self.modified = True

        # Update sampling rate
        self.sample_rate = float(sr)

        # Update sampling period
        if self.sample_rate != 0:
            self.sampling_period = 1 / self.sample_rate
        else:
            self.sampling_period = None

        # Update Conversion rate
        self.conversion_rate = self.sr_to_cr(sr)

        self.sr_specd = True

        if self.conversion_rate > CONV_RATE_LIMIT:
            logging.warning(
                "Your spec'd conversion rate"
                + " (%dKHz)" % (self.conversion_rate / 1000)
                + " exceeds the system's limit"
                + " (%dKHz)" % (CONV_RATE_LIMIT / 1000)
            )

        # Update delay config (dependent on conversion rate)
        self.update_delays()

    def update_sample_length(self, SL):
        # Establish parameters
        MAX_SAMPS = 18000

        # Set up variables
        SL = int(eval(SL))

        # Give user opportunity for a sanity check
        if SL >= MAX_SAMPS:
            logging.warning(
                "Your spec'd sample length"
                + " (%d samples) is greater and value tested before" % SL
                + " (%d samples). The BBB has been known to crash" % MAX_SAMPS
                + " when asking for 20000+ samples")

            raw_input("Hit enter to continue, or kill the program now: ")

        # Write argument to the ADC's settings
        self.sample_length = SL

    def update_deadband_ms(self, ms):
        logging.info("ADS7865: Deadband length set to %dms" % int(ms))
        self.deadband_ms = ms

    def update_threshold(self, desired_threshold):
        # Save desired_threshold value
        self.threshold = desired_threshold

        # Compute & save corrected threshold
        self.corrected_threshold = desired_threshold / self.digital_gain

    def update_digital_gain(self, desired_gain):
        # save argument
        self.digital_gain = desired_gain

        # Update threshold attribute to adjust self.corrected_threshold
        # to a value respresenting the new digital gain value
        self.update_threshold(self.threshold)
    
    def set_sample_len(self, sl):
        """ Sets the sample length

        Args:
            sl: sample length
        """
        self.sample_length = int(sl)

    def sw_reset(self):
        """
        """

        print("Performing ADC device reset...")
        self.config([CODE_SWRESET])

        # Immediate parameters that get defined at reset
        self.n_channels = 2

        # DAC outputs the default voltage
        self.dac_voltage = DEFAULT_DAC_VOLTAGE
        self.lsb = self.dac_voltage / (2**(WORD_SIZE - 1))  # Volts

        # Update sequencer and channel descriptions
        self.seq_desc = "CHA0" + PLUSMINUS + "/CHB0" + PLUSMINUS
        self.ch[0] = DIFF_PAIR_1
        self.ch[1] = DIFF_PAIR_3
        self.ch[2] = ''
        self.ch[3] = ''

        # Update other more complex parameters
        self.update_sample_rate(self.sampling_rate)

        # Update meta parameters
        self.modified = True

        # Let user know work is done
        print("... done.")

    def close(self):
        """
        """

        self._CS.write_to_port(1)
        self.DBus.close()
        self.WR.close()
        self._RD.close()
        # do not close # self.BUSY.close()
        self._CS.close()
        self._CONVST.close()
        
        # Disarming if applicable
        self.unready()

    ############################
    # General ADC Commands  #####
    ############################
    def update_config_text(self, seq, channels):
        """
        Takes the formatted strings seq and channels uses them to
        update internal parameters useful for printing out the
        config of the ADC.

        args:
            seq: string acting as a oneliner describing the ADC config.
            examples includes "CHA0+/CHB0+ -> CHA1+"/CH1+" or just
            "CHA0+/CHB0+"

            channels: list of string containing the same information
            embedded in seq, sans the "/" and "->" visual formatting
            stuff.
        """
        # Update human readable description
        self.seq_desc = seq

        # Update channel descriptions
        self.ch_idx = []
        for i in range(TOTAL_CHANNELS):
            self.ch[i] = channels[i]

            if self.ch[i] == DIFF_PAIR_1:
                self.ch_idx.append(1)
            elif self.ch[i] == DIFF_PAIR_2:
                self.ch_idx.append(2)
            elif self.ch[i] == DIFF_PAIR_3:
                self.ch_idx.append(3)
            elif self.ch[i] == DIFF_PAIR_4:
                self.ch_idx.append(4)
            elif self.ch[i] == '':
                pass  # Blank channel
            else:
                raise ValueError('ch "{0}" is an invalid '.format(channels[i])
                                 + "channel.")

    def V_to_12bit_Hex(self, Vin):
        """
        """
        return int(round(Vin / self.lsb))

    def dac_str_to_voltage(self, dac_s):
        """ Interprets the data 12 bit binary output of an ADC DAC read cmd,
        represented by the string dac_s
        """

        # DAC value Conversion Constant
        V_per_bit = 0.00244  # Volts/bit
        base_2 = 2

        dac_i = int(dac_s, base_2)
        dac_v = dac_i * V_per_bit

        return dac_v

    def cr_to_sr(self, cr):
        """
        """
        if self.n_channels != 0:
            return (cr * SAMPLES_PER_CONV) / float(self.n_channels)
        else:
            logging.warning("self.n_channels == 0. Unable to compute a sampleRate!")
            return None

    def sr_to_cr(self, sr):
        """
        """

        if self.n_channels != 0:
            return sr * (self.n_channels / float(SAMPLES_PER_CONV))
        else:
            logging.warning("self.n_channels == 0. Unable to compute a convRate!")
            return None

    def adc_status(self):
        """
        """

        # Read and write pins
        _RD = eval(self._RD.read_str())
        _WR = eval(self._RD.read_str())
        print("  _RD:\t%d" % _RD)
        print("  _WR:\t%d" % _WR)

        # Conversion and sample rate
        cr = self.conversion_rate
        print("  cr:\t%.2e conversions/sec" % cr)
        print("  sr:\t%.2e samples/sec" % self.sample_rate)

        # Sample length
        sl = self.sample_length
        print("  sl:\t%d samples" % sl)

        # Threshold
        print("  thr:\t%.1f Volts" % self.threshold)

        # arm status
        armed = self.arm_status
        print("  armed:\t%s" % armed)

        # channel config
        print("  config:\t{}".format(self.seq_desc))

        # get channels
        for i in range(4):
            print("  channel {}:\t{}".format(i, self.ch[i]))

    def gen_matching_time_array(self, M):
        """ For plotting signals in the time domain.

        Looks at it's sampling parameters, and generate a numpy array
        of length M to corresponds with M samples of data per channel
        """
        Ts = 1 / self.sample_rate

        if (M * Ts / Ts <= M):
            t = np.arange(0, M * Ts, Ts)

        elif (M * Ts / Ts > M):
            t = np.arange(0, (M - 0.1) * Ts, Ts)  # Chalk it up to precision error

        else:
            print("Something crazy happened.")
            t = None

        return t

    ############################
    #### PRUSS Commands  #######
    ############################
    def ready_pruss_for_burst(self, CR=None):
        """ Arms the ADC for sample collection. This removes some GPIO control
        from the BBB, and replaces it with PRUIN/OUT control.
        """

        # Initialize variables
        if CR is None:
            CR = self.conversion_rate
        else:
            self.conversion_rate = CR

        if CR == 0:
            raise ValueError("CR currently set to 0 (DEFAULT), indicating that"
                             + "user forgot to preset the sample/conversion rate."
                             + "prior to calling this function.")

        CR_BITECODE = int(round(1.0 / CR * F_CLK))  # Converts user CR input to Hex.

        # Initialize environment
        pypruss.modprobe()
        pypruss.init()      # Init the PRU
        pypruss.open(0)     # Open PRU event 0 which is PRU0_ARM_INTERRUPT
        pypruss.pruintc_init()  # Init the interrupt controller

        # init PRU Registers
        pypruss.exec_program(0, INIT0)  # Cleaning the registers
        pypruss.exec_program(1, INIT1)  # Cleaning the registers
        pypruss.pru_write_memory(0, 0x0000, [0x0, ] * 0x0800)  # clearing pru0 ram
        pypruss.pru_write_memory(0, 0x0800, [0x0, ] * 0x0800)  # clearing pru1 ram
        pypruss.pru_write_memory(0, 0x4000, [0x0, ] * 300)  # clearing ack bit from pru1
        pypruss.pru_write_memory(0, PRU0_CR_Mem_Offset, [CR_BITECODE, ])  # Setting conversion

        pypruss.exec_program(1, ADS7865_ClkAndSamplePRU)        # Load firmware on PRU1

        # end readying process by arming the PRUs
        boot.arm()
        self.arm_status = 'armed'
        self.modified = False

    def unready(self):
        """ Gives GPIO control back to the the beaglebone
        """

        if self.arm_status == 'unarmed':
            logging.warning("ADC Already dearmed!!! You are double dearming somewhere.")
        else:
            logging.warning('ADS7865: Dearming the PRUSS')
            boot.dearm()
            self.arm_status = 'unarmed'

    def reload(self):
        """ Re-initializes the PRU's interrupt that this library uses to tell
        python that it can continue running code again. This must be called at
        the end of a function that utilizes this interrupt. The calling
        function should not be responsible for reloading PRUs
        """
        pypruss.init()      # Init the PRU
        pypruss.open(0)     # Open PRU event 0 which is PRU0_ARM_INTERRUPT
        pypruss.pruintc_init()  # Init the interrupt controller

    def burst(self, length=None, n_channels=None, raw=None, fmt_volts=1):
        """
        Args:
            length: Number of samples to record. Overides natural behavior to
          use the value stored in self.length

            n_channels: Number of channel that will collect samples. overrides
          natural behavior to use the value storing in self.n_channels

            raw: Bit that lets the user specify that he wants the data in the
          raw binary non-2's compliment format instead of 2's compliment.

            fmt_volts: Specify's whether to convert the raw binary data into
          human readable volts form.

        """
        if length is None:  # Optional argument for sample length
            length = self.sample_length
        else:
            self.sample_length = int(length)

        if n_channels is None:
            n_channels = self.n_channels
        else:
            self.n_channels = n_channels

        # Share DDR RAM Addr with PRU0
        pypruss.pru_write_memory(0, PRU0_DDR_MEM_OFFSET, [self.ddr['addr'], ])

        # Share SL with PRU0: pru_SL_mapping just incorporates
        # some math that translates the user specified SL parameter
        # to a byte addressable memory size value that the PRU will use to
        # check whether it has finished writing it's data to the
        # memory
        pru_SL_mapping = (length - MIN_SAMPLE_LENGTH) * BYTES_PER_SAMPLE
        pypruss.pru_write_memory(0, PRU0_SL_MEM_OFFSET, [pru_SL_mapping, ])

        # Share deadband length with PRU0
        db_hex = int(round(self.deadband_ms / 1000.0 * F_CLK * 2.0))  # counts
        pypruss.pru_write_memory(0, PRU0_DB_MEM_OFFSET, [db_hex, ])

        # Share Threshold with PRU0
        thr_hex = self.V_to_12bit_Hex(self.corrected_threshold)
        pypruss.pru_write_memory(0, PRU0_THR_Mem_Offset, [thr_hex, ])

        # Launch the Sample collection program
        a = time.time()
        pypruss.exec_program(0, ADS7865_MasterPRU)  # Load firmware on PRU0

        # Wait for PRU to finish its job.
        pypruss.wait_for_event(0)  # Wait for event 0 which is conn to PRU0_ARM_INTERRUPT
        b = time.time()
        t = b - a

        # Once signal has been received, clean up house
        # pypruss.clear_event(0) # Clear the event
        # pypruss.exit()         # Exit PRU

        # Read the memory: Extract raw status code
        raw_data = read_sample(self.ddr, length + STATUS_BLOCK)
        logging.info("ADC: RAW_DATA %d:" % raw_data[0])
        status_code = raw_data[0] & 0x3F

        # Read the memory: Extract TOF Flag
        TOF = get_bit(raw_data[0], TIMEOUT_STATUS_BIT)
        self.TOF = TOF

        # Read the memory: Extract TRG_CH Data
        self.TRG_CH = get_bit(raw_data[0], TFLG0_BIT)
        print
        if self.n_channels != 2:
            self.TRG_CH += 2 * get_bit(raw_data[0], TFLG1_BIT)
        logging.info("ADC: Triggered off ch %d" % self.TRG_CH)
        

        # Read the DB overflow bit
        DBOVF = get_bit(raw_data[0], DBOVF_BIT)
        logging.info("ADC: DBOVF = %d" % DBOVF)

        # Read the memory: Move on. Treat actual data as raw data now.
        raw_data = raw_data[1:]

        # Print out stuff
        logging.info("ADC: Returned Status code = %d" % status_code)
        logging.info("ADC: Returned TOF code = %d" % TOF)
        if TOF:
            logging.warning("ADC: TIMEOUT occured!")

        y_orig = y = [0] * n_channels
        for chan in range(n_channels):

            # user may specify whether he wants a numpy array
            # ... or not.
            y[chan] = np.asarray(raw_data[chan::n_channels])

            # User may specify whether he wants values to come in
            # raw, or two's compliment.
            if raw is None or raw == 0:
                i = 0
                for sample in y[chan]:
                    y[chan][i] = twos_comp(sample, WORD_SIZE)
                    i += 1

                # Assuming that the user is requesting 2 compliment values,
                # it is possible to do conversion to voltage values. How ever,
                # if the user has set raw to True, then this option is
                # unavailable.
                if fmt_volts:
                    y[chan] = y[chan] * self.lsb

                    # Apply digital gain
                    y_orig[chan] = y[chan]
                    y[chan] = y[chan] * self.digital_gain

        # Perform some commands that ready the ADC for another burst.
        self.reload()

        # Storing collected samples internally
        self.y = y
        self.y_orig = y_orig

        # Return values
        return (y, TOF)

    def get_data(self):
        """Simplifies the process of getting data when it's requested. This
        method will typically replace any use of "self.burst()" and deciding
        whether or not you have to arm the ADC or not.
        """

        if self.arm_status != 'armed' or self.modified is True:
            self.ready_pruss_for_burst()

        y, TOF = self.burst()

        if TOF == False:
            return y
        else:
            return None


class ADC_Tools():

    def meas_vpp(self, ADC):
        """Computes the vpp for each channel that the ADC is using.
        """
        # initialize variables
        vpp = []

        # Compute the vpp for each channel
        for ch in range(ADC.n_channels):
            vpp.append(np.amax(ADC.y[ch]) - np.amin(ADC.y[ch]))
        
        # Return tuple containing the data
        return tuple(vpp)

    def find_local_maxima(self, a):
        """
        args:
            y = array (numpy or list) of values
        """

        # Initial arrays and bits
        peaks = []
        rising_bit = 0

        for i in range(1, a.size):
            prev_value = a[i - 1]

            if rising_bit:
                # was previously on local rise. Now checking if slope goes negative.
                if (a[i] - prev_value < 0):
                    # Peak found. Save it. Reset the rising_bit
                    peaks.append(i - 1)
                    rising_bit = 0

            else:
                # Looking for local rise.
                if (a[i] - prev_value) > 0:
                    rising_bit = 1

        return peaks
