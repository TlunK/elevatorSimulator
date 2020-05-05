import time
import math
from collections import defaultdict
from tkinter import *
from tkinter import messagebox
import socket
from multiprocessing import Process
import matplotlib.pyplot as plt

# config will be loaded from server
MAX_FLOOR = 0
MIN_FLOOR = 0
NUM_FLOOR = 0  # MAX_FLOOR - MIN_FLOOR + 1  # including ground floor
NUM_ELEVATOR = 0
ELEVATOR_CAPACITY = 0
NUM_ORDER = 0
PORT = 54000

# graphic config
ELEVATOR_WIDTH = 0
ELEVATOR_HEIGHT = 0
ORDER_WIDTH = 0

# canvas position
LEFT_P = 0
TOP_P = 0

GROUND_FLOOR_TOP = 0

# global variables
elevator_list = []
canvas_elevator_status = []
canvas_cabin = []
canvas_cabin_coords = []
canvas_counter = None
current_time = 0
finished_order_count = 0
waiting_orders = defaultdict(list)
waiting_orders_canvas_objects = []

finish = False


class Order(object):
    def __init__(self, from_floor, to_floor, status):
        self.from_floor = from_floor
        self.to_floor = to_floor
        self.status = status


class Elevator(object):
    STATUS_GOING_UP = 1
    STATUS_GOING_DOWN = 2
    STATUS_IDLE = 3
    STATUS_LOADING = 4
    STATUS_UNLOADING = 5

    def __init__(self, capacity, canvas, index, rectangle, top):
        self.carrying_orders = []
        self.rectangle = rectangle
        self.top = top
        self.canvas = canvas
        self.capacity = capacity
        self.index = index

        self.cabin = []
        self.UI_status = Elevator.STATUS_IDLE



def percentile(data, percentile):
    size = len(data)
    return sorted(data)[int(math.ceil((size * percentile) / 100)) - 1]


def int_to_status(s):
    if s == 1:
        return Elevator.STATUS_GOING_UP
    elif s == 2:
        return Elevator.STATUS_GOING_DOWN
    elif s == 3:
        return Elevator.STATUS_IDLE
    elif s == 4:
        return Elevator.STATUS_LOADING
    elif s == 5:
        return Elevator.STATUS_UNLOADING
    else:
        raise Exception("??")


def floor_to_offset(floor):
    return MAX_FLOOR - floor


def status_to_color_text(status):
    if status == Elevator.STATUS_IDLE:
        return "yellow", "idle"
    elif status == Elevator.STATUS_GOING_UP:
        return "green", "up"
    elif status == Elevator.STATUS_GOING_DOWN:
        return "cyan", "down"
    elif status == Elevator.STATUS_LOADING:
        return "red", "load"
    elif status == Elevator.STATUS_UNLOADING:
        return "white", "unload"


def redraw_elevator_status(canvas):
    for ele in elevator_list:
        s = ele.UI_status
        if s != canvas_elevator_status[ele.index][0]:
            _, rect, text = canvas_elevator_status[ele.index]
            canvas.delete(rect)
            canvas.delete(text)

            i = ele.index
            color, txt = status_to_color_text(s)
            rect = canvas.create_rectangle(LEFT_P + ELEVATOR_WIDTH * i, TOP_P - ELEVATOR_HEIGHT - 5,
                                           LEFT_P + ELEVATOR_WIDTH * (i + 1), TOP_P - 5,
                                           fill=color)

            text = canvas.create_text(LEFT_P + ELEVATOR_WIDTH * i, TOP_P - ELEVATOR_HEIGHT - 5, anchor=NW, text=txt,
                                      font=('TimesNewRoman', 11))

            x_offset = findXCenter(canvas, ELEVATOR_WIDTH, text)
            canvas.move(text, x_offset, 0)

            canvas_elevator_status.append((Elevator.STATUS_IDLE, rect, text))

            canvas_elevator_status[ele.index] = (s, rect, text)


def findXCenter(canvas, width, item):
    coords = canvas.bbox(item)
    xOffset = (width / 2) - ((coords[2] - coords[0]) / 2)
    return xOffset


def draw_building(master, w):
    w.create_rectangle(LEFT_P, TOP_P, LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR, TOP_P + ELEVATOR_HEIGHT * NUM_FLOOR,
                       fill="white")

    # draw elevator status
    for i in range(NUM_ELEVATOR):
        s = Elevator.STATUS_IDLE
        color, txt = status_to_color_text(s)
        rect = w.create_rectangle(LEFT_P + ELEVATOR_WIDTH * i, TOP_P - ELEVATOR_HEIGHT - 5,
                                  LEFT_P + ELEVATOR_WIDTH * (i + 1), TOP_P - 5,
                                  fill=color)

        text = w.create_text(LEFT_P + ELEVATOR_WIDTH * i, TOP_P - ELEVATOR_HEIGHT - 5, anchor=NW, text=txt,
                             font=('TimesNewRoman', 11))

        x_offset = findXCenter(w, ELEVATOR_WIDTH, text)
        w.move(text, x_offset, 0)

        canvas_elevator_status.append((Elevator.STATUS_IDLE, rect, text))

    # draw vertical lines
    for i in range(1, NUM_ELEVATOR):
        w.create_line(LEFT_P + i * ELEVATOR_WIDTH, TOP_P, LEFT_P + i * ELEVATOR_WIDTH,
                      ELEVATOR_HEIGHT * NUM_FLOOR + TOP_P)

    # draw floor lines
    for i in range(1, NUM_FLOOR):
        w.create_line(LEFT_P, ELEVATOR_HEIGHT * i + TOP_P, LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR,
                      ELEVATOR_HEIGHT * i + TOP_P)

    # draw floor text
    for i in range(NUM_FLOOR):
        floor = MAX_FLOOR - i
        if floor == 0:
            floor = "G"
        else:
            floor = str(floor) + "F"

        w.create_text(LEFT_P - 50, ELEVATOR_HEIGHT * i + TOP_P, anchor=NW, text=floor, font=('TimesNewRoman', 11))

    master.update()
    print("Draw Building Finished")


def init_and_draw_elevators(canvas):
    global elevator_list

    # draw elevators
    for i in range(NUM_ELEVATOR):
        rect = canvas.create_rectangle(LEFT_P + ELEVATOR_WIDTH * i,
                                       GROUND_FLOOR_TOP,
                                       LEFT_P + ELEVATOR_WIDTH * (i + 1),
                                       GROUND_FLOOR_TOP + ELEVATOR_HEIGHT, outline='red', width="4")

        elevator = Elevator(ELEVATOR_CAPACITY, canvas, i, rect, GROUND_FLOOR_TOP)
        elevator_list.append(elevator)


def draw_cabin(canvas):
    left = LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR + 150
    for i in range(NUM_ELEVATOR):
        canvas.create_text(
            left, TOP_P - 20 + 100 * i, anchor=NW,
            text="Elevator #" + str(i) + " cabin",
            font=('TimesNewRoman', 10), fill="black")

        rect_top = TOP_P + 100 * i
        canvas.create_rectangle(left, TOP_P + 100 * i,
                                left + 200,
                                TOP_P + 100 * (i + 1) - 40, outline='black', width="4", fill="white")
        canvas_cabin_coords.append((left, rect_top))
        canvas_cabin.append([])


def draw_counter(canvas):
    global canvas_counter
    left = LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR + 150
    canvas_counter = canvas.create_text(
        left, TOP_P - 20 + 100 * NUM_ELEVATOR, anchor=NW,
        text="Completed Orders: " + str(finished_order_count) + "/" + str(NUM_ORDER),
        font=('TimesNewRoman', 12), fill="black")


def redraw_waiting_orders(canvas):
    global waiting_orders_canvas_objects
    # clean first
    for rect, text in waiting_orders_canvas_objects:
        canvas.delete(rect)
        canvas.delete(text)

    waiting_orders_canvas_objects = []

    for floor in range(MIN_FLOOR, MAX_FLOOR + 1):
        orders = waiting_orders[floor]
        for offset, order in enumerate(orders):
            left = LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR + 5
            top = TOP_P + floor_to_offset(order.from_floor) * ELEVATOR_HEIGHT + 2
            rect = canvas.create_rectangle(
                left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5,
                top + ORDER_WIDTH,
                fill="red", outline='red')
            text = canvas.create_text(
                left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text=str(order.to_floor),
                font=('TimesNewRoman', 10), fill="white")

            waiting_orders_canvas_objects.append((rect, text))


def redraw_cabin_orders(canvas):
    global canvas_cabin
    global canvas_cabin_coords
    for i in range(NUM_ELEVATOR):
        # wipe out all orders
        for rect, text in canvas_cabin[i]:
            canvas.delete(rect)
            canvas.delete(text)
        canvas_cabin[i] = []

        left, top = canvas_cabin_coords[i]
        left = left + 5
        top = top + 5
        offset = 0
        for order in elevator_list[i].cabin:
            if order.status == 2:
                rect = canvas.create_rectangle(
                    left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5,
                    top + ORDER_WIDTH,
                    fill="yellow", outline='yellow')
                text = canvas.create_text(
                    left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text="out",
                    font=('TimesNewRoman', 7), fill="red")
            elif order.status == 1:
                rect = canvas.create_rectangle(
                    left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5,
                    top + ORDER_WIDTH,
                    fill="green", outline='green')
                text = canvas.create_text(
                    left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text="in",
                    font=('TimesNewRoman', 10), fill="white")
            else:
                rect = canvas.create_rectangle(
                    left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5,
                    top + ORDER_WIDTH,
                    fill="red", outline='red')
                text = canvas.create_text(
                    left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text=str(order.to_floor),
                    font=('TimesNewRoman', 10), fill="white")

            x_offset = findXCenter(canvas, ORDER_WIDTH, text)
            canvas.move(text, x_offset, 0)

            canvas_cabin[i].append((rect, text))
            offset += 1


def update_elevator_on_canvas(elevator, canvas):
    rect_top = canvas.coords(elevator.rectangle)[1]
    if rect_top != elevator.top:
        canvas.move(elevator.rectangle, 0, elevator.top - rect_top)


def parse_config(data):
    data = data.decode("ascii")
    global MAX_FLOOR, MIN_FLOOR, NUM_FLOOR, NUM_ELEVATOR, ELEVATOR_CAPACITY, NUM_ORDER, ELEVATOR_WIDTH, ELEVATOR_HEIGHT, ORDER_WIDTH, LEFT_P, TOP_P, GROUND_FLOOR_TOP
    MAX_FLOOR, MIN_FLOOR, NUM_FLOOR, NUM_ELEVATOR, ELEVATOR_CAPACITY, NUM_ORDER, ELEVATOR_WIDTH, ELEVATOR_HEIGHT, ORDER_WIDTH, LEFT_P, TOP_P = [int(s) for s in data.split(",")[:-1]]
    GROUND_FLOOR_TOP = TOP_P + MAX_FLOOR * ELEVATOR_HEIGHT


def show_plot():
    time.sleep(1)  # wait for plot data
    f = open('data_analysis.csv')
    waiting_time = []
    cabin_time = []
    total_time = []
    for line in f.readlines():
        create_time, load_time, unload_time = [int(t) for t in line.split(",")]
        waiting_time.append(load_time - create_time)
        cabin_time.append(unload_time - load_time)
        total_time.append(unload_time - create_time)

    fig, ax = plt.subplots(3, sharex="all")
    fig.canvas.set_window_title('Order Time Analysis')

    num_bins = min(max(len(set(waiting_time)), 10), 20)
    # the histogram of the data
    ax[0].hist(waiting_time, num_bins, alpha=0.7, edgecolor='black')
    average0 = sum(waiting_time) * 1.0 / len(waiting_time)
    ax[0].axvline(average0, color='k', linestyle='dashed', linewidth=1)
    ax[0].text(average0, 0, 'avg', rotation=90)
    percent_90_0 = percentile(waiting_time, 90)
    ax[0].axvline(percent_90_0, color='k', linestyle='dashed', linewidth=1)
    ax[0].text(percent_90_0, 0, '90%', rotation=90)
    percent_95_0 = percentile(waiting_time, 95)
    ax[0].axvline(percent_95_0, color='k', linestyle='dashed', linewidth=1)
    ax[0].text(percent_95_0, 0, '95%', rotation=90)
    percent_99_0 = percentile(waiting_time, 99)
    ax[0].axvline(percent_99_0, color='k', linestyle='dashed', linewidth=1)
    ax[0].text(percent_99_0, 0, '99%', rotation=90)

    ax[0].set_xlabel('seconds')
    ax[0].set_ylabel('# of orders')
    ax[0].set_title("Waiting Time (Before pick up)")

    num_bins = max(len(set(cabin_time)), 10)
    ax[1].hist(cabin_time, num_bins, alpha=0.7, edgecolor='black')
    average1 = sum(cabin_time) * 1.0 / len(cabin_time)
    ax[1].axvline(average1, color='k', linestyle='dashed', linewidth=1)
    ax[1].text(average1, 0, 'avg', rotation=90)
    percent_90_1 = percentile(cabin_time, 90)
    ax[1].axvline(percent_90_1, color='k', linestyle='dashed', linewidth=1)
    ax[1].text(percent_90_1, 0, '90%', rotation=90)
    percent_95_1 = percentile(cabin_time, 95)
    ax[1].axvline(percent_95_1, color='k', linestyle='dashed', linewidth=1)
    ax[1].text(percent_95_1, 0, '95%', rotation=90)
    percent_99_1 = percentile(cabin_time, 99)
    ax[1].axvline(percent_99_1, color='k', linestyle='dashed', linewidth=1)
    ax[1].text(percent_99_1, 0, '99%', rotation=90)

    ax[1].set_xlabel('seconds')
    ax[1].set_ylabel('# of orders')
    ax[1].set_title("Cabin Time (Time spent in an elevator)")


    num_bins = max(len(set(total_time)), 10)
    ax[2].hist(total_time, num_bins, alpha=0.7, edgecolor='black')
    average2 = sum(total_time) * 1.0 / len(total_time)
    ax[2].axvline(average2, color='k', linestyle='dashed', linewidth=1)
    ax[2].text(average2, 0, 'avg', rotation=90)
    percent_90_2 = percentile(total_time, 90)
    ax[2].axvline(percent_90_2, color='k', linestyle='dashed', linewidth=1)
    ax[2].text(percent_90_2, 0, '90%', rotation=90)
    percent_95_2 = percentile(total_time, 95)
    ax[2].axvline(percent_95_2, color='k', linestyle='dashed', linewidth=1)
    ax[2].text(percent_95_2, 0, '95%', rotation=90)
    percent_99_2 = percentile(total_time, 99)
    ax[2].axvline(percent_99_2, color='k', linestyle='dashed', linewidth=1)
    ax[2].text(percent_99_2, 0, '99%', rotation=90)

    ax[2].set_xlabel('seconds')
    ax[2].set_ylabel('# of orders')
    ax[2].set_title("Total Time (Total time to finish an order)")

    plt.tight_layout()
    plt.show()


def parse_data(data):
    data = data.decode("ascii")
    data = [int(s) for s in data.split(",")[:-1]]
    i = 0

    try:
        # update elevator
        for ele in elevator_list:
            ele.index = data[i]
            ele.top = data[i+1]
            ele.UI_status = int_to_status(data[i+2])

            # update elevator cabin
            i = i + 3
            cabin_size = data[i]
            ele.cabin = []
            i += 1
            for j in range(cabin_size):
                ele.cabin.append(Order(data[i + 3 * j], data[i + 3 * j + 1], data[i + 3 * j + 2]))

            i = i + cabin_size * 3

        global finished_order_count
        finished_order_count = data[i]
        i += 1

        for floor in range(MIN_FLOOR, MAX_FLOOR + 1):
            length = int(data[i])
            i += 1
            orders = []
            for j in range(length):
                orders.append(Order(floor, data[i + j], 0))

            i += length
            waiting_orders[floor] = orders
    except Exception as e:
        print(e)
        print(data)


def main2(prev_window):
    prev_window.destroy()

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    retry = 3
    success = False
    ex = None
    while retry > 0:
        try:
            # Connect the socket to the port where the server is listening
            server_address = ('localhost', PORT)
            print('connecting to %s port %s' % server_address)
            sock.connect(server_address)
            success = True
        except Exception as e:
            ex = e
            retry -= 1
            time.sleep(0.3)

    if not success:
        raise ex

    message = '?'
    print("Requesting configs")
    sock.sendall(message.encode("ascii"))

    data = sock.recv(4096)
    print('received "%s"' % data)
    parse_config(data)

    # init canvas
    master = Tk()
    canvas = Canvas(master, width=900, height=950)
    canvas.pack()
    draw_building(master, canvas)
    init_and_draw_elevators(canvas)
    draw_cabin(canvas)
    draw_counter(canvas)

    prev_finished_order_count = 0
    has_shown_plot = False
    while True:
        # request simulation info
        message = '?'
        sock.sendall(message.encode("ascii"))
        data = sock.recv(8192)
        parse_data(data)

        # update elevator position
        for ele in elevator_list:
            update_elevator_on_canvas(ele, canvas)
        # redraw waiting orders on each floor
        redraw_waiting_orders(canvas)
        redraw_elevator_status(canvas)
        redraw_cabin_orders(canvas)
        if finished_order_count != prev_finished_order_count:
            prev_finished_order_count = finished_order_count
            canvas.delete(canvas_counter)
            draw_counter(canvas)

        if finished_order_count == NUM_ORDER and not has_shown_plot:
            has_shown_plot = True
            show_plot()

        master.update()
        time.sleep(0.01)

    # TODO
    # show result
    mainloop()


def run_server(command, args):
    print("run_server: ", command)
    print(args)
    import os
    os.execv(command, args)


def main():
    window = Tk()
    window.title("Elevator Simulator")

    label = Label(window, text="Window could be not large enough to display all floors, but simulation still works.")
    label.pack()

    frame = Frame(window)
    frame.pack()

    start_row = 0
    label = Label(frame, text="Max Floor")
    label.grid(row=0, column=0)
    MAX_FLOOR_entry = Entry(frame, width=5)
    MAX_FLOOR_entry.insert(0, "30")
    MAX_FLOOR_entry.grid(row=0, column=1)

    label = Label(frame, text="Min Floor")
    label.grid(row=start_row + 1, column=0)
    MIN_FLOOR_entry = Entry(frame, width=5)
    MIN_FLOOR_entry.insert(0, "-3")
    MIN_FLOOR_entry.grid(row=start_row + 1, column=1)

    start_row -= 1

    label = Label(frame, text="Number of Elevators")
    label.grid(row=start_row + 3, column=0)
    NUM_ELEVATOR_entry = Entry(frame, width=5)
    NUM_ELEVATOR_entry.insert(0, "3")
    NUM_ELEVATOR_entry.grid(row=start_row + 3, column=1)

    label = Label(frame, text="Elevator Capacity")
    label.grid(row=start_row + 4, column=0)
    ELEVATOR_CAPACITY_entry = Entry(frame, width=5)
    ELEVATOR_CAPACITY_entry.insert(0, "10")
    ELEVATOR_CAPACITY_entry.grid(row=start_row + 4, column=1)

    label = Label(frame, text="Number of Orders")
    label.grid(row=start_row + 5, column=0)
    NUM_ORDER_entry = Entry(frame, width=5)
    NUM_ORDER_entry.insert(0, "10")
    NUM_ORDER_entry.grid(row=start_row + 5, column=1)

    label = Label(frame, text="Generate Order Interval(MS)")
    label.grid(row=start_row + 6, column=0)
    order_interval_entry = Entry(frame, width=5)
    order_interval_entry.insert(0, "500")
    order_interval_entry.grid(row=start_row + 6, column=1)

    label = Label(frame, text="Loading Unloading Time Per Order(MS)")
    label.grid(row=start_row + 7, column=0)
    loading_unloading_entry = Entry(frame, width=5)
    loading_unloading_entry.insert(0, "500")
    loading_unloading_entry.grid(row=start_row + 7, column=1)

    label = Label(frame, text="TCP port")
    label.grid(row=start_row + 8, column=0)
    PORT_entry = Entry(frame, width=5)
    PORT_entry.insert(0, "53000")
    PORT_entry.grid(row=start_row + 8, column=1)

    def run():
        global MAX_FLOOR, MIN_FLOOR, NUM_ELEVATOR, NUM_ORDER, ELEVATOR_CAPACITY, PORT

        t = MAX_FLOOR_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "MAX_FLOOR is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "MAX_FLOOR > 0")
            return
        MAX_FLOOR = t

        t = MIN_FLOOR_entry.get()
        if not t.lstrip("-").isdigit():
            messagebox.showinfo("invalid parameter", "MIN_FLOOR is integer")
            return
        t = int(t)
        if t >= 0:
            messagebox.showinfo("invalid parameter", "MIN_FLOOR < 0")
            return
        MIN_FLOOR = t

        t = NUM_ELEVATOR_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "MAX_FLOOR is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "MAX_FLOOR > 0")
            return
        NUM_ELEVATOR = t

        t = ELEVATOR_CAPACITY_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "ELEVATOR_CAPACITY is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "ELEVATOR_CAPACITY > 0")
            return
        ELEVATOR_CAPACITY = t

        t = NUM_ORDER_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "NUM_ORDER is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "NUM_ORDER > 0")
            return
        NUM_ORDER = t

        t = order_interval_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "generate order interval is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "generate order interval > 0")
            return
        order_interval = t

        t = loading_unloading_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "Loading Unloading Time is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "Loading Unloading Time > 0")
            return
        loading_unloading = t

        t = PORT_entry.get()
        if not t.isdigit():
            messagebox.showinfo("invalid parameter", "PORT is integer")
            return
        t = int(t)
        if t <= 0:
            messagebox.showinfo("invalid parameter", "PORT > 0")
            return
        PORT = t

        command = "server.exe "

        # server = subprocess.Popen("exec " + command, stdout=subprocess.PIPE, shell=True)
        server = Process(target=run_server, args=(command,
            [command, str(MAX_FLOOR), str(MIN_FLOOR), str(NUM_ELEVATOR), str(ELEVATOR_CAPACITY), str(NUM_ORDER), str(PORT), str(order_interval), str(loading_unloading)]))
        server.start()

        # parent()
        time.sleep(0.1)  # wait for server to start
        try:
            main2(window)
        finally:
            server.terminate()
            server.join()

    def test1():
        MAX_FLOOR_entry.delete(0, END)
        MIN_FLOOR_entry.delete(0, END)
        NUM_ELEVATOR_entry.delete(0, END)
        ELEVATOR_CAPACITY_entry.delete(0, END)
        NUM_ORDER_entry.delete(0, END)
        order_interval_entry.delete(0, END)
        loading_unloading_entry.delete(0, END)

        MAX_FLOOR_entry.insert(0, "30")
        MIN_FLOOR_entry.insert(0, "-3")
        NUM_ELEVATOR_entry.insert(0, "3")
        ELEVATOR_CAPACITY_entry.insert(0, "30")
        NUM_ORDER_entry.insert(0, "50")
        order_interval_entry.insert(0, "1000")
        loading_unloading_entry.insert(0, "1000")

        messagebox.showinfo("Info", "Parameters updated")

    test1_btn = Button(frame, text="Predefined Test Case #1", command=test1)
    test1_btn.grid(row=start_row + 9, column=0)

    def test2():
        MAX_FLOOR_entry.delete(0, END)
        MIN_FLOOR_entry.delete(0, END)
        NUM_ELEVATOR_entry.delete(0, END)
        ELEVATOR_CAPACITY_entry.delete(0, END)
        NUM_ORDER_entry.delete(0, END)
        order_interval_entry.delete(0, END)
        loading_unloading_entry.delete(0, END)

        MAX_FLOOR_entry.insert(0, "20")
        MIN_FLOOR_entry.insert(0, "-10")
        NUM_ELEVATOR_entry.insert(0, "5")
        ELEVATOR_CAPACITY_entry.insert(0, "30")
        NUM_ORDER_entry.insert(0, "50")
        order_interval_entry.insert(0, "800")
        loading_unloading_entry.insert(0, "800")

        messagebox.showinfo("Info", "Parameters updated")

    test2_btn = Button(frame, text="Predefined Test Case #2", command=test2)
    test2_btn.grid(row=start_row + 10, column=0)

    def test3():
        MAX_FLOOR_entry.delete(0, END)
        MIN_FLOOR_entry.delete(0, END)
        NUM_ELEVATOR_entry.delete(0, END)
        ELEVATOR_CAPACITY_entry.delete(0, END)
        NUM_ORDER_entry.delete(0, END)
        order_interval_entry.delete(0, END)
        loading_unloading_entry.delete(0, END)

        MAX_FLOOR_entry.insert(0, "30")
        MIN_FLOOR_entry.insert(0, "-3")
        NUM_ELEVATOR_entry.insert(0, "6")
        ELEVATOR_CAPACITY_entry.insert(0, "30")
        NUM_ORDER_entry.insert(0, "200")
        order_interval_entry.insert(0, "300")
        loading_unloading_entry.insert(0, "500")

        messagebox.showinfo("Info", "Parameters updated")

    test3_btn = Button(frame, text="Predefined Test Case #3", command=test3)
    test3_btn.grid(row=start_row + 11, column=0)

    def test4():
        MAX_FLOOR_entry.delete(0, END)
        MIN_FLOOR_entry.delete(0, END)
        NUM_ELEVATOR_entry.delete(0, END)
        ELEVATOR_CAPACITY_entry.delete(0, END)
        NUM_ORDER_entry.delete(0, END)
        order_interval_entry.delete(0, END)
        loading_unloading_entry.delete(0, END)

        MAX_FLOOR_entry.insert(0, "30")
        MIN_FLOOR_entry.insert(0, "-3")
        NUM_ELEVATOR_entry.insert(0, "2")
        ELEVATOR_CAPACITY_entry.insert(0, "30")
        NUM_ORDER_entry.insert(0, "200")
        order_interval_entry.insert(0, "700")
        loading_unloading_entry.insert(0, "500")

        messagebox.showinfo("Info", "Parameters updated")

    test4_btn = Button(frame, text="Predefined Test Case #4", command=test4)
    test4_btn.grid(row=start_row + 12, column=0)

    submit = Button(frame, text="Run Simulation", command=run, bg="red")
    submit.grid(row=start_row + 13, column=0)

    mainloop()


if __name__ == '__main__':
    main()
