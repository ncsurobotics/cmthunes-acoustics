import os

def load():
	# enable all pins to be used as io
	os.system("config-pin overlay cape-universal")
	os.system("config-pin overlay cape-univ-hdmi")
	
def arm():
	os.system("config-pin P8.27 pruin") #DB0	#PRU1
	os.system("config-pin P8.28 pruin") #DB1	#PRU1
	os.system("config-pin P8.29 pruin") #DB2	#PRU1
	os.system("config-pin P8.39 pruin") #DB3	#PRU1
	os.system("config-pin P8.40 pruin") #DB4	#PRU1
	os.system("config-pin P8.41 pruin") #DB5	#PRU1
	os.system("config-pin P8.42 pruin") #DB6	#PRU1
	os.system("config-pin P8.43 pruin") #DB7	#PRU1
	os.system("config-pin P8.44 pruin") #DB8	#PRU1
	os.system("config-pin P8.45 pruin") #DB9	#PRU1
	os.system("config-pin P8.46 pruout") #DB10	#PRU1
	os.system("config-pin P9.26 pruin") #DB11	#PRU1

	os.system("config-pin P9.29 pruout") # bCONVST	#PRU0
	os.system("config-pin P9.31 pruout") # bWR		#PRU0
	os.system("config-pin P9.30 pruout") # bRD		#PRU0
	os.system("config-pin P9.27 pruin")	# BUSY		#PRU0
	
def dearm():
	os.system("config-pin P8.27 gpio") #DB0
	os.system("config-pin P8.28 gpio") #DB1
	os.system("config-pin P8.29 gpio") #DB2
	os.system("config-pin P8.39 gpio") #DB3
	os.system("config-pin P8.40 gpio") #DB4
	os.system("config-pin P8.41 gpio") #DB5
	os.system("config-pin P8.42 gpio") #DB6
	os.system("config-pin P8.43 gpio") #DB7
	os.system("config-pin P8.44 gpio") #DB8
	os.system("config-pin P8.45 gpio") #DB9
	os.system("config-pin P8.46 gpio") #DB10
	os.system("config-pin P9.26 gpio") #DB11

	os.system("config-pin P9.29 gpio") # bCONVST
	os.system("config-pin P9.31 gpio") # bWR
	os.system("config-pin P9.30 gpio") # bRD
	os.system("config-pin P9.27 gpio") # BUSY
