import pypruss		#Python PRUSS wrapper
import mmap
import struct
import boot			#
import time			#sleep
import BBBIO		#Yields functions for working with GPIO
import settings		#Same function as a .YAML file
import numpy as np

#Global ADC program Constants
PRU0_SR_Mem_Offset = 3
HC_SR = 0xBEBC200
fclk = 200e6

BIN = settings.bin_directory
INIT0 = BIN+"init0.bin"
INIT1 = BIN+"init1.bin"
ADS7865_MasterPRU = BIN+"ADS7865_sample.bin"
ADS7865_ClkAndSamplePRU = BIN+"pru1.bin"
WORD_SIZE = 12

BYTES_PER_SAMPLE = 4
MIN_SAMPLE_LENGTH = 2
DEFAULT_DAC_VOLTAGE = 2.49612

CODE_READDAC = 0x103
CODE_SWRESET = 0x105
CODE_READSEQ = 0x106

#Global Functions
def Read_Sample(user_mem, Sample_Length):
	print("ADC: Still have to write documentation about the structure of user_mem variable...")
	
	with open("/dev/mem", "r+b") as f:	# Open the physical memory device
		ddr_mem = mmap.mmap(f.fileno(), user_mem['filelen'], offset=user_mem['offset']) # mmap the right area

	y = []
	for i in range(Sample_Length):
		a = user_mem['start']+i*4
		b = a+4
		c = struct.unpack("L", ddr_mem[a:b])[0]	# Parse the data
		y = y + [c,]
		#print(c)
		
	return y
		
def twos_comp(val, bits):
        """compute the 2's compliment of int value val, of n bits."""
        if( (val&(1<<(bits-1))) != 0 ):
          val = val - (1<<bits)
        return val


######################################
######    ADS7865 Class ##############
#####################################

DB_pin_table = ['P9_26','P8_46','P8_45','P8_44','P8_43','P8_42','P8_41','P8_40','P8_39','P8_29','P8_28','P8_27']
WR_pin = 'P9_31'
BUSY_pin = 'P9_27'
CS_pin = 'P9_25'
RD_pin = 'P9_30'
CONVST_pin = 'P9_29'

class ADS7865:
	"""
	ADS7865: Class that allows the user to instantiate an object 
	representing the system ADS7865, an analog to digital converter
	IC by Texas Instruments. The object incorporates attributes
	relating to ADC's config, and function for changing the config
	as well as functions for collecting a string of samples in
	realtime. """

	def __init__(self, SR=0, L=0):
		"""Initialization will configure several BBB pins as necessary
		to hold the adc in an idle state. """
	
		#GPIO Stuff
		self.DBus = BBBIO.Port(DB_pin_table)
		self.DBus.setPortDir("in")
		
		self.WR = BBBIO.Port(WR_pin)
		self.WR.setPortDir("out")
		self.WR.writeToPort(1)
		
		self._RD = BBBIO.Port(RD_pin)
		self._RD.setPortDir("out")
		self._RD.writeToPort(1)

		self._CONVST = BBBIO.Port(CONVST_pin)
		self._CONVST.setPortDir("out")
		self._CONVST.writeToPort(1)
		
		self._CS = BBBIO.Port(CS_pin)
		self._CS.setPortDir("out")
		self._CS.writeToPort(0)
		
		
		self.n_channels = 2
	
		#PRUSS Stuff
		self.ddr = {}
		self.ddr['addr'] = pypruss.ddr_addr()
		self.ddr['size'] = pypruss.ddr_size()
		self.ddr['start'] = 0x10000000
		self.ddr['filelen'] = self.ddr['size']+0x10000000
		self.ddr['offset'] = self.ddr['addr']-0x10000000
		self.ddr['end'] =  0x10000000+self.ddr['size']
		
		print("ADS7865: Allowing one 32bit memory block per sample, it is "
			+ "possible to collect %.1fK Samples in a single burst. These "
			% (self.ddr['size']/1000)
			+ "sample points are stored in DDRAM, which is found at the "
			+ "address range starting at %s" % (hex(self.ddr['addr'])))
		
		self.sampleRate = SR
		self.sampleLength = int(L)
		self.arm_status = "unknown"
		
		#Load overlays: Does not configure any GPIO to pruin or pruout
		boot.load()
		self.SW_Reset()
		
	############################
	#### GPIO Commands  #######
	############################
	def Config(self, cmd_list):
		"""Config: Method that takes a list of hex values (cmd_list)
		and bitbangs the ADC accordingly. User may refer to the
		datasheet for an explanation of what the hex values actually
		mean. Additionally, user may refer to (self).EZConfig for
		examples of how to correctly apply this command."""

		# Callee save the port direction
		#callee_sPD = self.DBus.portDirection
		
		# 
		for cmd in cmd_list:
			self.WR.writeToPort(0)		#Open ADC's input Latch
		
			self.DBus.setPortDir("out")	#Latch open, safe to make DB pins an out
			self.DBus.writeToPort(cmd)	#Write the value to the DB pins
			
			print('ADS7865: Databus cmd %s has been sent.' % self.DBus.readStr())
			self.WR.writeToPort(1)		#Latch down the input
		
		self.DBus.setPortDir("in")#Return DB pins back to inputs.
	
	def EZConfig(self, sel):
		"""EZConfig: method allowing the user to access commonly
		used config command (presets). sel is an integer from 0 to 5
		representing a particular preset."""

		#NOTES TO USER
		#--At powerup, sequencer_register=0x000
		#--Capturing one channel (non-pair) in isolation is doable by selecting sel=0
		#or sel=1 (since ADS7865 resets the data_output pointer at the beginning of every
		#CONVST), but the user must also take the extra precaution to disable the
		#"sub-sampling" portion of the PRUSS code in order for it to work.
	
		#Single channel (pair) enable
		if sel==0:
			#User has chosen to sample the 0a/0b differential channel pair.
			self.Config([0x100])
		elif sel==1:
			#User has chosen to sample the 1a/1b differential channel pair.
			self.Config([0xD00])

		#Single channel (pair) enable with sequencer reinitialization
		elif sel==2:
			#User has chosen to sample the 0a/0b differential channel pair 
			#while disabling the sequencer register
			self.Config([0x104,0x000])
		elif sel==3:
			#User has chosen to sample the 0a/0b differential channel pair 
			#while disabling the sequencer register
			self.Config([0x304,0x000])
			
		#Dual channel (pair) enable
		elif sel==4:
			#User has chosen to sample the 0a/0b -> 1a/1b in FIFO style
			self.Config([0x104,0x230])
		elif sel==5:
			#User has chosen to sample the 1a/1b -> 0a/0b in FIFO style
			self.Config([0x104,0x2c0])
		elif sel==6:
			self.Config([0x104,0x290])
			
	def Read_Seq(self):
		# Send cmd telling ADC to output it's SEQ config
		self.Config([CODE_READSEQ])
		
		# Read ADC's databus
		self._RD.writeToPort(0)
		seq = self.DBus.readStr()
		self._RD.writeToPort(1)
		
		# print config to the user
		print("Config of sequencer: %s" % seq)
		
	def Read_Dac(self):
		# Send cmd telling ADC to output it's SEQ config
		self.Config([CODE_READDAC])
		
		# Read ADC's databus
		self._RD.writeToPort(0)
		dac_s = self.DBus.readStr()
		self._RD.writeToPort(1)
		
		# print config to the user
		print("Config of DAC: %s" % dac_s)
		
		# interpret value
		dac_voltage_readout = self.Conv_Dac_Str_to_Voltage(dac_s)
		print("... Vdac = %.5f volts" % dac_voltage_readout)
		
		# Update DAC related atributes
		self.dacVoltage = dac_voltage_readout
		self.LSB = self.dacVoltage/(2**(WORD_SIZE-1)) #Volts
	
	def SW_Reset(self):
		print("Performing ADC device reset...")
		self.Config([CODE_SWRESET])
		
		# DAC outputs the default voltage
		self.dacVoltage = DEFAULT_DAC_VOLTAGE
		self.LSB = self.dacVoltage/(2**(WORD_SIZE-1)) #Volts
		
		# Let user know work is done
		print("... done.")
			
	def Close(self):
		self._CS.writeToPort(1)
		self.DBus.close()
		self.WR.close()
		self._RD.close()
		#self.BUSY.close()
		self._CS.close()
		self._CONVST.close()
	
	############################
	# General ADC Commands  #####
	############################
	def Conv_Dac_Str_to_Voltage(self, dac_s):
		"""Conv_Dac_Str_to_Voltage: Method for interpreting the data
		12 bit binary output of an ADC DAC read cmd, represented
		by the string dac_s."""
		
		# DAC value Conversion Constant
		V_per_bit = 0.00244 #Volts/bit
		base_2 = 2
		
		dac_i = int(dac_s, base_2)
		dac_v = dac_i*V_per_bit
		
		return dac_v
		
	
	############################
	#### PRUSS Commands  #######
	############################
	def Ready_PRUSS_For_Burst(self, SR=None):
		# Initialize variables
		if SR is None:
			SR = self.sampleRate
		else:
			self.sampleRate = SR
			
		if SR == 0:
			print("SR currently set to 0. Please specify a sample rate.")
			exit(1)
			
		SR_BITECODE = int(round(1.0/SR*fclk)) # Converts user SR input to Hex.
		
		# Initialize evironment
		pypruss.modprobe()	
		pypruss.init()		# Init the PRU
		pypruss.open(0)		# Open PRU event 0 which is PRU0_ARM_INTERRUPT
		pypruss.pruintc_init()  # Init the interrupt controller

		# INIT PRU Registers	
		pypruss.exec_program(0, INIT0) # Cleaning the registers
		pypruss.exec_program(1, INIT1) # Cleaning the registers	
		pypruss.pru_write_memory(0, 0x0000, [0x0,]*0x0800) # clearing pru0 ram
		pypruss.pru_write_memory(0, 0x0800, [0x0,]*0x0800) # clearing pru1 ram
		pypruss.pru_write_memory(0, 0x4000, [0x0,]*300) # clearing ack bit from pru1
		pypruss.pru_write_memory(0, PRU0_SR_Mem_Offset, [SR_BITECODE,]) # Setting samplerate
		
		pypruss.exec_program(1, ADS7865_ClkAndSamplePRU) 		# Load firmware on PRU1
		
		# end readying process by arming the PRUs
		boot.arm()

	def Reload(self):
		"""This method re-initializes the PRU's interrupt that this
		library uses to tell python that it can continue running code again.
		This must be called at the end of a function that utilizes this
		interrupt. The calling function should not be responsible for
		reloading PRUs."""
		pypruss.init()		# Init the PRU
		pypruss.open(0)		# Open PRU event 0 which is PRU0_ARM_INTERRUPT
		pypruss.pruintc_init()  # Init the interrupt controller
	
	def Burst(self, length=None, n_channels=None, raw=None, fmt_volts=1):
		if length is None:				#Optional argument for sample length
			length = self.sampleLength
		else:
			self.sampleLength = int(length)
		
		if n_channels is None:
			n_channels = self.n_channels
		else:
			self.n_channels = n_channels
			
		#Share DDR RAM Addr with PRU0
		pypruss.pru_write_memory(0, 1, [self.ddr['addr'],])
		
		#Share SL with PRU0: pru_SL_mapping just incorporates
		#some math that translates the user specified SL parameter
		#to a byte addressible memory size value that the PRU will use to
		#check whether it has finished writing it's data to the
		#memory
		pru_SL_mapping = (length - MIN_SAMPLE_LENGTH) * BYTES_PER_SAMPLE
		pypruss.pru_write_memory(0, 2, [pru_SL_mapping,])
		
		#Launch the Sample collection program
		a = time.time()
		pypruss.exec_program(0, ADS7865_MasterPRU) # Load firmware on PRU0
		
		# Wait for PRU to finish its job.
		pypruss.wait_for_event(0)# Wait for event 0 which is conn to PRU0_ARM_INTERUPT	
		b = time.time()
		t = b-a

		#Once signal has been received, clean up house
		#pypruss.clear_event(0)	# Clear the event
		#pypruss.exit()			# Exit PRU
		
		# Read the memory
		raw_data = Read_Sample(self.ddr, length)
		

		y = [0]*n_channels
		for chan in range(n_channels):
		
			# user may specify whether he wants a numpy array
			# ... or not.
			y[chan] = np.asarray(raw_data[chan::n_channels])
			
		
			# User may specify whether he wants values to come in
			# raw, or two's compliment.
			if (raw == None) or (raw == 0):
				i = 0
				for samp in y[chan]:
					y[chan][i] = twos_comp(samp,WORD_SIZE)
					i += 1
					
				# Assuming that the user is requesting 2 compliment values,
				# it is possible to do conversion to voltage values. How ever,
				# if the user has set raw to True, then this option is 
				# unavailable.
				if fmt_volts:
					y[chan] = y[chan] * self.LSB
				
			
		self.Reload()
		return y,t
