import matplotlib.pyplot as plt



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    filename = "ch3_sw15_long.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()


    float_vals = [float(i.split()[3]) for i in lines]

    times = [i/746.2 for i in range(len(float_vals))]
    

    plt.scatter(times, float_vals, s=2)
    plt.title(filename)
    plt.xlabel("Time (s)")
    plt.ylabel("Current (uA)")
    plt.show()