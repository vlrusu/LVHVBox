import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    
    filename = "temp.txt"
    #filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_vals = [i for i in float_vals if i<200]
    float_vals = np.array(float_vals)
    float_vals -= float_vals.mean()
    


    #freq = 235.85E3
    #float_vals = [np.sin(2*np.pi*freq*i/235.85E3) for i in range(8000)]
    times = [i/163E3 for i in range(len(float_vals))]

    plt.scatter(times, float_vals, s=2)
    plt.ylim((-3,3))
    plt.show()