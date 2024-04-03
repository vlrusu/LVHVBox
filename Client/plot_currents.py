import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    
    filename = "spark2_ch1.txt"
    #filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_valch2_4s = [i for i in float_vals]
    float_vals = np.array(float_vals)
    std = np.std(float_vals)
    #float_vals -= float_vals.mean()
    print(float_vals)
    


    #freq = 235.85E3
    #float_vals = [np.sin(2*np.pi*freq*i/235.85E3) for i in range(8000)]

    #times = [i/163E3 for i in range(len(float_vals))]
    times = [i/108.7E3 for i in range(len(float_vals))]

    plt.scatter(times, float_vals, s=2)
    plt.title("Standard deviation: " + str(round(std, 3)) + " uA")
    #plt.ylim((-0.25,0.25))
    plt.show()