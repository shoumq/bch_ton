from matplotlib import pyplot as plt

months = list(range(1, 13))
revenue = [52, 74, 79, 95, 115, 110, 129, 126, 147, 146, 156, 184]

def get_gradient_at_b(x, y, b, k):
    N = len(x)
    diff = 0
    for i in range(N):
        diff += (y[i] - (k * x[i] + b))
    return -2 / N * diff


def get_gradient_at_k(x, y, b, k):
    N = len(x)
    diff = 0
    for i in range(N):
        diff += x[i] * (y[i] - (k * x[i] + b))
    return -2 / N * diff


def step_gradient(x, y, b_current, k_current, learning_rate=0.05):
    b_gradient = get_gradient_at_b(x, y, b_current, k_current)
    k_gradient = get_gradient_at_k(x, y, b_current, k_current)
    b = b_current - b_gradient * learning_rate
    k = k_current - k_gradient * learning_rate
    return b, k


def gradient_descent(x, y, num_iterations, learning_rate=0.05):
    b = 0
    k = 0
    for i in range(num_iterations):
        b, k = step_gradient(x, y, b, k, learning_rate)
    return b, k


def main():
    b, k = gradient_descent(months, revenue, 1000, 0.01)
    print(b, k)
    plt.scatter(months, revenue)
    plt.plot(months, [k * x + b for x in months])
    plt.show()

if __name__ == '__main__':
    main()