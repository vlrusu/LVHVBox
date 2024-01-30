import matplotlib.pyplot as plt
import math
import numpy as np



if __name__=="__main__":
    '''
    #filename = "full_currents_1728949092.txt"
    filename = "sw50_long_100ptcorrection.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    float_vals = [i for i in float_vals]
    '''




    
    with open('peds1000.txt') as f:
        lines = f.readlines()
        float_vals = [float(line.split()[2]) for line in lines if float(line.split()[1]) > 140]
        #float_vals = [float(line.split()[0]) for line in lines]
    









    plt.hist(float_vals,100)

    plt.title(np.std(float_vals))


    plt.show()