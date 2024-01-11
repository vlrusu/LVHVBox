import matplotlib.pyplot as plt



if __name__=="__main__":
    #filename = "full_currents_1728949092.txt"
    filename = "full_currents_1705005037.txt"

    f = open(filename, "r")
    lines = f.readlines()
    f.close()

    float_vals = [float(i) for i in lines]
    

    plt.scatter(range(len(float_vals)), float_vals, s=2)
    plt.show()