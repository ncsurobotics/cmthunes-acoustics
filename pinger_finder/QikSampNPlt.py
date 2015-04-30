import boot
import numpy as np
SAMPLES_PER_CONV = 2


def main(ADC_obj, plt):
    ADC_obj.Ready_PRUSS_For_Burst()

    #print("ADC is armed and ready.")
    #raw_input("Press enter when ready...")

    # grab data
    (y, temp) = ADC_obj.Burst()

    plot_output(ADC_obj, y, plt)

    ADC_obj.Unready()
    return y


def plot_output(ADC_obj, y, plt):
    # get plotting objects
    fig, ax = plt.subplots()
    ax.hold(True)

    # Compute parameters
    n = ADC_obj.n_channels
    M = y[0].size

    fs = ADC_obj.sampleRate

    t = ADC_obj.Generate_Matching_Time_Array(M)

    # Plot the data
    legend_list = [''] * ADC_obj.n_channels
    for chan in range(ADC_obj.n_channels):
        ax.plot(t, y[chan])
        legend_list[chan] = ADC_obj.ch[chan]
        plt.xlabel('time (seconds)')
        plt.ylabel('Voltage')
        plt.title('Voltage vs Time, Fs=%dKHz' % (fs / 1000))

    ax.axis(xmin=0,
            xmax=None,
            ymin=-2.5,
            ymax=2.5)

    ax.legend(legend_list)
    plt.show()
