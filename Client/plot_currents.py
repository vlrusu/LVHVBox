import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    
    filename = "full_currents_1705949681.txt"
    #filename = "full_currents_1705610740.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    


    #freq = 235.85E3
    #float_vals = [np.sin(2*np.pi*freq*i/235.85E3) for i in range(8000)]
    

    plt.scatter(range(len(float_vals)), float_vals, s=2)
    plt.show()