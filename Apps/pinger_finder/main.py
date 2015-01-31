import ADC
import time
from sys import argv

def Shoot(ADC,len,SR):
	# Initialize empty variables
	sum = 0

	# Used ADC to collect samples
	raw_input("Hit enter when you're ready...")
	y,t = ADC.Burst(len)

	# Interpret data
	samples = len - 1
	Ts = t/ ((samples/2)-1)
	print("")
	print("main: %d samples were captured in %.2e seconds (the first 2 samples are usually a freebies). That's %.2f us/samplePair (not counting the freebie pair). That's a %.2fHz experiment." % (samples, t, 1e6*Ts, 1/Ts))
	print("")
	print("main: (1 - Actual_Rate/Intended_Rate) = %.2f%%." % ((1-(1/Ts)/SR)*100))

	# Tell the user if he has any useful data
	print("")
	for i in y:
		sum += i
	print("main: The sum of all your samples is %d" % sum)

	# Return the raw y incase needed for more analysis.
	#import pdb; pdb.set_trace()
	return y

########################
#### MAIN PROGRAM ######
########################

# Parse user input: Aquire sample length
Samp_len = int(argv[1])

# Parse user input: Acquire sampling rate
if len(argv) < 3:
	print("main: You did not specify a sample rate")
	SR = input("Please enter a sample rate (samps/sec): ")
else:
	SR = int(argv[2])

### Configure there ADC
# create an object for ADS7865
ADS7865 = ADC.ADS7865()
"""Instantiating the ADS7865 also ran code for building in attributes for 
running commands relevent to the ADC"""
if len(argv) > 3:
	# Configure settings
	#ADS7865.Config([0xF0F,])
	#ADS7865.Config([0xF0F,0x0F0])
	ADS7865.EZConfig(0)
else:
	print("\nmain: user did not give 4th argument. I will skip over any configuration steps.")

# All settings have been configured. Beaglebone is ready for arming.
ADS7865.Ready_PRUSS_For_Burst(SR)
"""At this point pruss module has been initialized, PRUSS-RAM has been
wiped, and PRU1 firmware is loaded and running (PRU1 will idle until PRU0
comes online to recognize and clear a CINT bit)."""
y = Shoot(ADS7865,Samp_len,SR)
