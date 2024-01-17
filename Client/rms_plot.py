import matplotlib.pyplot as plt
import math
import numpy as np



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    filename = "full_currents_1705047485.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_vals = [i for i in float_vals]
    

    plt.hist(float_vals,100)

    plt.title(np.std(float_vals))


    plt.show()