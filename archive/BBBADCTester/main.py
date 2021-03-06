import BBBIO
import ADC
import export
import time


def twos_comp(val, bits):
    """compute the 2's compliment of int value val"""
    if((val & (1 << (bits - 1))) != 0):
        val = val - (1 << bits)
    return val


def main():
    # settings
    scope = 'FULL'
    DB_pin_table = ['P8_08', 'P8_09', 'P8_10', 'P8_11', 'P8_12', 'P8_13', 'P8_14', 'P8_15', 'P8_16', 'P8_17', 'P8_18', 'P8_19']
    WR_pin = 'P9_11'
    BUSY_pin = 'P9_12'
    CS_pin = 'P9_13'
    RD_pin = 'P9_14'
    CONVST_pin = 'P9_15'

    leave = False

    # program
    io = {'PortDB': BBBIO.Port(DB_pin_table),
          '/WR': BBBIO.Port(WR_pin),
          'BUSY': BBBIO.Port(BUSY_pin),
          '/CS': BBBIO.Port(CS_pin),
          '/RD': BBBIO.Port(RD_pin),
          '/CONVST': BBBIO.Port(CONVST_pin),
          }

    # ADC initialization
    ADS7865 = ADC.ADS7865(io)
    ADS7865.Init_ADC()
    #import pdb; pdb.set_trace()

    ##########
    ## LOOP ##
    ##########
    while leave is False:
        # Select experiment
        experiment = 'trace CH1'
        if experiment == 'trace CH1':
            ADS7865.Configure(256)  # 0x100
        if experiment == 'trace CH1 and CH2':
            ADS7865.Configure(300)  # 0x104;
            ADS7865.Configure(2304)  # 0x900

        n = 0
        data = []
        a = time.time()
        while n < 1000:
            # Start conversion
            ADS7865.StartConv()
            result = ADS7865.ReadConv()

            b = time.time()
            if n == 0:
                t0 = b - a

            t = (b - a - t0)

            trace = twos_comp(int(result, 2), len(result))

            print(trace)
            data.append((t, trace))
            n += 1

        export.RunCSVExport(data)
        leave = True
    ADS7865.Close()

if __name__ == '__main__':
    main()
