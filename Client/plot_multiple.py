import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt


if __name__ == "__main__":
    # filename = "full_currents_1728949092.txt"

    filename = "temp0_1.txt"
    # filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_valch2_4s = [i for i in float_vals]
    float_vals_0 = np.array(float_vals)

    filename = "temp1_1.txt"
    # filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_valch2_4s = [i for i in float_vals]
    float_vals_1 = np.array(float_vals)

    """
    filename = "temp2.txt"
    #filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_valch2_4s = [i for i in float_vals]
    float_vals_2 = np.array(float_vals)
    """

    # freq = 235.85E3
    # float_vals = [np.sin(2*np.pi*freq*i/235.85E3) for i in range(8000)]

    # times = [i/163E3 for i in range(len(float_vals))]
    # times = [i/108.7E3 for i in range(len(float_vals))]
    times = [i for i in range(len(float_vals))]

    ch0 = plt.scatter(times, float_vals_0, s=10, label="Ch0")
    ch1 = plt.scatter(times, float_vals_1, s=10, label="Ch1")
    # ch2 = plt.scatter(times, float_vals_2, s=10, label='Ch2')

    plt.legend()

    plt.xlabel("Datapoint")
    plt.ylabel("Current (uA)")
    plt.title("Full Speed Currents With Ch0 Spark")
    # plt.xlim([0.036, 0.0385])
    # plt.xlim([3400,4200])
    # plt.xlim([3950,4100])
    # plt.ylim((-0.25,0.25))
    plt.show()
