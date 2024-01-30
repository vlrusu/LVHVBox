

import numpy as np

from scipy.fft import fft, fftfreq, ifft

import matplotlib.pyplot as plt

 

# Open file and read data into numpy array

filename = "sw18_noped.txt"
    #filename = "full_currents_1705610740.txt"

f = open(filename, "r")
lines = f.readlines()
f.close()

data = [float(i) for i in lines]

data = np.array([i for i in data if i<200 and i>25])





'''
with open('sw50_ped_long_1.txt') as f:
    lines = f.readlines()
    #data = [float(line.split()[0]) for line in lines if float(line.split()[0]) > 20]
    data = [float(line.split()[0]) for line in lines]
    data = [i for i in data if i<1000 and i>0]
data = np.array(data)
'''



 

# Separate time column from signal column

#time = [(1./794.6) * i for i in range(len(data))]
time = [(1./163400) * i for i in range(len(data))]

plt.scatter(time,data)
plt.show()


#time = (1./109.7E3) * data[:, 0]

#time = (1e-6*243057./8192.) * data[:, 0]


'''
N = 8000
ix = np.arange(N)
freq = 235.85E3
data = np.sin(2*np.pi*ix/235.85E3*freq)
'''







signal = data

signal = signal - signal.mean()

 

print(time[1]-time[0])

# Calculate FFT of signal column

fft_signal = ifft(signal)

 

# Calculate the frequency values for each FFT coefficient

freq = fftfreq(len(signal), d=time[1]-time[0])

 

# Plot the FFT results


plt.plot(freq, abs(fft_signal)**2)
plt.xlim((-100,120000))
#plt.xlim((-10,300))

plt.xlabel('Frequency (Hz)')

plt.ylabel('Amplitude Squared')

plt.title("Power distribution in frequency domain")

plt.show()