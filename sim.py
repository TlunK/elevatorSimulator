import random
import threading
import time
from collections import defaultdict
from tkinter import *

# config
MAX_FLOOR = 30
MIN_FLOOR = -3
NUM_FLOOR = MAX_FLOOR - MIN_FLOOR + 1  # including ground floor
NUM_ELEVATOR = 3
ELEVATOR_CAPACITY = 5
NUM_ORDER = 10

# speed config
# elevator speed is one pixel per loop
ELEVATOR_MOVE_INTERVAL = 0.01  # time in seconds that elevator moves by one pixel
LOADING_UNLOADING_TIME = 2  # time in seconds that loading or unloading passengers takes
ORDER_GENERATE_INTERVAL = 1  # time in seconds between new orders

# graphic config
ELEVATOR_WIDTH = 50
ELEVATOR_HEIGHT = 25
ORDER_WIDTH = 21

# canvas position
LEFT_P = 70
TOP_P = 60

GROUND_FLOOR_TOP = TOP_P + MAX_FLOOR * ELEVATOR_HEIGHT
MIN_FLOOR_TOP = TOP_P + (MAX_FLOOR - MIN_FLOOR) * ELEVATOR_HEIGHT

# global variables
elevator_list = []
canvas_elevator_status = []
canvas_cabin = []
canvas_cabin_coords = []
canvas_counter = None
redraw_cabin_queue = []
current_time = 0
finished_order_count = 0
finished_order_count_lock = threading.Lock()
waiting_orders = defaultdict(list)
draw_new_order_queue = []
redraw_waiting_orders_queue = []
waiting_orders_canvas_objects = defaultdict(list)
waiting_orders_locks = {}
for floor_n in range(MIN_FLOOR, MAX_FLOOR + 1):
    waiting_orders_locks[floor_n] = threading.Lock()
finish = False


class Order(object):
    def __init__(self, from_floor, to_floor, create_time, ID):
        self.from_floor = from_floor
        self.to_floor = to_floor

        self.create_time = create_time
        self.finish_time = None
        self.board_time = None
        self.id = ID


class Elevator(object):
    STATUS_GOING_UP = 1
    STATUS_GOING_DOWN = 2
    STATUS_IDLE = 3
    STATUS_LOADING = 4
    STATUS_UNLOADING = 5

    def __init__(self, capacity, canvas, index, rectangle, top, floor):
        self.carrying_orders = []
        self.rectangle = rectangle
        self.top = top
        self.canvas = canvas
        self.capacity = capacity
        self.index = index

        self.cabin = []
        self.status = Elevator.STATUS_IDLE
        self.UI_status = Elevator.STATUS_IDLE
        self.floor = floor

        self.going_down_target_floor = None
        self.going_up_target_floor = None

    def print_cabin(self):
        print("ele id: " + str(self.index) + "cabin: " + ", ".join(
            [str((order.from_floor, order.to_floor)) for order in self.cabin]))

    def set_going_down_target_floor(self, floor):
        if self.going_down_target_floor is None:
            self.going_down_target_floor = floor
        else:
            self.going_down_target_floor = min(self.going_down_target_floor, floor)

    def set_going_up_target_floor(self, floor):
        if self.going_up_target_floor is None:
            self.going_up_target_floor = floor
        else:
            self.going_up_target_floor = max(self.going_up_target_floor, floor)

    def get_current_floor(self):
        top = self.top

        if (top - TOP_P) % ELEVATOR_HEIGHT != 0:
            return self.floor

        floor_id = int((top - TOP_P) / ELEVATOR_HEIGHT)

        return MAX_FLOOR - floor_id

    def elevator_thread(self):
        while True:
            if finish:
                return

            if self.status == Elevator.STATUS_GOING_UP:
                self.going_up()
            elif self.status == Elevator.STATUS_GOING_DOWN:  # TODO: other status
                self.going_down()
            else:
                self.idle()

            time.sleep(ELEVATOR_MOVE_INTERVAL)

    def going_up(self):
        cur_floor = self.get_current_floor()

        # reached a new floor
        if self.floor != cur_floor:
            self.floor = cur_floor
            self.unload()
            self.load()

        if self.floor == self.going_up_target_floor or self.floor == MAX_FLOOR:  # reached target floor, go to idle or go down
            if len(self.cabin) != 0:
                self.print_cabin()
                raise Exception("bug")

            self.going_up_target_floor = None

            # go down to pickup orders
            if self.going_down_target_floor is not None:
                self.status = Elevator.STATUS_GOING_DOWN
                self.UI_status = Elevator.STATUS_GOING_DOWN
                self.load()
            else:
                # try to load orders
                self.status = Elevator.STATUS_GOING_DOWN
                self.UI_status = Elevator.STATUS_GOING_DOWN
                self.load()
                if len(self.cabin) == 0:  # no orders, go to idle
                    self.status = Elevator.STATUS_IDLE
                    self.UI_status = Elevator.STATUS_IDLE
        else:  # going up
            self.top -= 1

    def going_down(self):
        cur_floor = self.get_current_floor()
        # reached a new floor
        if self.floor != cur_floor:
            self.floor = cur_floor
            self.unload()
            self.load()

        if self.floor == self.going_down_target_floor or self.floor == MIN_FLOOR:  # reached target floor, go to idle or go up
            if len(self.cabin) != 0:
                self.print_cabin()
                raise Exception("bug")

            # no more orders going down
            self.going_down_target_floor = None

            # go up to pickup orders or idle
            if self.going_up_target_floor is not None:
                self.status = Elevator.STATUS_GOING_UP
                self.UI_status = Elevator.STATUS_GOING_UP
                self.load()
            else:
                # try to load orders
                self.status = Elevator.STATUS_GOING_UP
                self.UI_status = Elevator.STATUS_GOING_UP
                self.load()
                if len(self.cabin) == 0:  # no orders, go to idle
                    self.status = Elevator.STATUS_IDLE
                    self.UI_status = Elevator.STATUS_IDLE
        else:  # going down
            self.top += 1

    def idle(self):
        if self.going_down_target_floor is not None:
            self.status = Elevator.STATUS_GOING_DOWN
            self.UI_status = Elevator.STATUS_GOING_DOWN
            self.load()
        elif self.going_up_target_floor is not None:
            self.status = Elevator.STATUS_GOING_UP
            self.UI_status = Elevator.STATUS_GOING_UP
            self.load()

    def unload(self):
        self.UI_status = Elevator.STATUS_UNLOADING
        cur_floor = self.get_current_floor()

        # unload passenger
        new_cabin = []
        for order in self.cabin:
            if order.to_floor == cur_floor:
                self.finish_order(order)
                time.sleep(LOADING_UNLOADING_TIME)
            else:
                new_cabin.append(order)

        if len(self.cabin) != len(new_cabin):
            add_redraw_cabin(self.index)

        self.cabin = new_cabin

        self.UI_status = self.status

    def load(self):
        self.UI_status = Elevator.STATUS_LOADING
        cur_floor = self.get_current_floor()
        new_cabin = self.cabin

        # load passenger that goes to the same direction
        floor_lock = waiting_orders_locks[cur_floor]
        floor_lock.acquire()
        orders = waiting_orders[cur_floor]
        new_waiting_orders = []
        count = 0
        for order in orders:
            if len(new_cabin) >= self.capacity:
                if order.to_floor > cur_floor and self.status == Elevator.STATUS_GOING_UP:
                    reschedule_elevator(order)
                if order.to_floor < cur_floor and self.status == Elevator.STATUS_GOING_DOWN:
                    reschedule_elevator(order)

                new_waiting_orders.append(order)
                continue

            if order.to_floor > cur_floor and self.status == Elevator.STATUS_GOING_UP:
                new_cabin.append(order)
                self.set_going_up_target_floor(order.to_floor)
                count += 1
            elif order.to_floor < cur_floor and self.status == Elevator.STATUS_GOING_DOWN:
                new_cabin.append(order)
                self.set_going_down_target_floor(order.to_floor)
                count += 1
            else:  # not going to same direction
                new_waiting_orders.append(order)

        waiting_orders[cur_floor] = new_waiting_orders
        floor_lock.release()

        if count > 0:
            time.sleep(LOADING_UNLOADING_TIME * count)
            add_redraw_waiting_orders(cur_floor)
            add_redraw_cabin(self.index)

        self.cabin = new_cabin
        self.UI_status = self.status


    def finish_order(self, order):
        print("Order finished: ", order.from_floor, order.to_floor)

        global finished_order_count
        finished_order_count = finished_order_count + 1
        print(finished_order_count)


def reschedule_elevator(order):
    # TODO: implementation
    print("Order need to reschedule elevator: ", order.from_floor, order.to_floor)


class OrderGenerator(object):
    def __init__(self, interval):
        self.last_order_time = -interval
        self.interval = interval
        self.increment_ID = 0

    def rand_order(self, cur_time):
        from_floor = random.randint(MIN_FLOOR, MAX_FLOOR)
        to_floor = random.randint(MIN_FLOOR, MAX_FLOOR)

        while to_floor == from_floor:  # to_floor must be different
            to_floor = random.randint(MIN_FLOOR, MAX_FLOOR)

        self.increment_ID = self.increment_ID + 1
        order = Order(from_floor, to_floor, cur_time, self.increment_ID)
        return order

    def generate_order(self, cur_time):
        return self.rand_order(cur_time)


def floor_to_offset(floor):
    return MAX_FLOOR - floor


def add_redraw_cabin(i):
    global redraw_cabin_queue
    redraw_cabin_queue.append(i)


def add_redraw_waiting_orders(floor):
    global redraw_waiting_orders_queue
    redraw_waiting_orders_queue.append(floor)


def calculate_elevator_order_distance(order, ele):
    is_going_up = order.from_floor < order.to_floor
    if is_going_up:
        if ele.status == Elevator.STATUS_GOING_UP:
            if order.from_floor > ele.floor:
                distance = order.from_floor - ele.floor
            else:
                distance = MAX_FLOOR - ele.floor + MAX_FLOOR - order.from_floor
        elif ele.status == Elevator.STATUS_GOING_DOWN:
            distance = ele.floor - MIN_FLOOR + order.from_floor - MIN_FLOOR
        else:
            distance = abs(ele.floor - order.from_floor)

    else:
        if ele.status == Elevator.STATUS_GOING_DOWN:
            if order.from_floor < ele.floor:
                distance = ele.floor - order.from_floor
            else:
                distance = ele.floor - MIN_FLOOR + order.from_floor
        elif ele.status == Elevator.STATUS_GOING_UP:
            distance = MAX_FLOOR - ele.floor + MAX_FLOOR - order.from_floor
        else:
            distance = abs(ele.floor - order.from_floor)
    return distance


def schedule_order(order, ele):
    if order.from_floor > ele.floor:
        ele.set_going_up_target_floor(order.from_floor)
    else:
        ele.set_going_down_target_floor(order.from_floor)


def order_generator_thread():
    global draw_new_order_queue
    global current_time

    print("order_generator_thread started")
    order_generator = OrderGenerator(ORDER_GENERATE_INTERVAL)
    counter = 0
    while True:
        if finish or counter >= NUM_ORDER:
            return

        # generate new order
        order = order_generator.generate_order(current_time)
        if order:
            counter += 1
            print("new order ", order.from_floor, order.to_floor, counter)

            waiting_list = waiting_orders[order.from_floor]
            offset = len(waiting_list)

            draw_new_order_queue.append((order, offset))

            waiting_orders[order.from_floor] = waiting_list + [order]

            # pick a closest elevator
            min_distance = calculate_elevator_order_distance(order, elevator_list[0])
            winner = elevator_list[0]
            for ele in elevator_list[1:]:
                distance = calculate_elevator_order_distance(order, ele)
                if distance < min_distance:
                    winner = ele

            schedule_order(order, winner)

        time.sleep(ORDER_GENERATE_INTERVAL)


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

        elevator = Elevator(ELEVATOR_CAPACITY, canvas, i, rect, GROUND_FLOOR_TOP, 0)
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
        left, TOP_P - 20 + 100 * 3, anchor=NW,
        text="Completed Orders: " + str(finished_order_count) + "/" + str(NUM_ORDER),
        font=('TimesNewRoman', 12), fill="black")


def draw_new_order(canvas):
    global draw_new_order_queue
    global waiting_orders_canvas_objects
    while draw_new_order_queue:
        new_order, offset = draw_new_order_queue[0]
        draw_new_order_queue = draw_new_order_queue[1:]

        left = LEFT_P + ELEVATOR_WIDTH * NUM_ELEVATOR + 5
        top = TOP_P + floor_to_offset(new_order.from_floor) * ELEVATOR_HEIGHT + 2
        rect = canvas.create_rectangle(
            left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5, top + ORDER_WIDTH,
            fill="red", outline='red')
        text = canvas.create_text(
            left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text=str(new_order.to_floor),
            font=('TimesNewRoman', 10), fill="white")

        # record canvas objects
        canvas_objs = waiting_orders_canvas_objects[new_order.from_floor]
        canvas_objs.append(rect)
        canvas_objs.append(text)
        waiting_orders_canvas_objects[new_order.from_floor] = canvas_objs


def redraw_cabin(canvas):
    global redraw_cabin_queue
    global canvas_cabin
    global canvas_cabin_coords
    while redraw_cabin_queue:
        i = redraw_cabin_queue[0]
        redraw_cabin_queue = redraw_cabin_queue[1:]

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
            rect = canvas.create_rectangle(
                left + offset * (ORDER_WIDTH + 5), top, left + (offset + 1) * ORDER_WIDTH + offset * 5,
                top + ORDER_WIDTH,
                fill="red", outline='red')
            text = canvas.create_text(
                left + offset * (ORDER_WIDTH + 5) + 1, top + 2, anchor=NW, text=str(order.to_floor),
                font=('TimesNewRoman', 10), fill="white")

            canvas_cabin[i].append((rect, text))
            offset += 1


def redraw_waiting_orders(canvas):
    global redraw_waiting_orders_queue
    global waiting_orders_canvas_objects
    while redraw_waiting_orders_queue:
        floor = redraw_waiting_orders_queue[0]
        redraw_waiting_orders_queue = redraw_waiting_orders_queue[1:]

        # wipe out all orders
        for obj in waiting_orders_canvas_objects[floor]:
            canvas.delete(obj)
        waiting_orders_canvas_objects[floor] = []
        canvas.update()
        # redraw
        for offset, order in enumerate(waiting_orders[floor]):
            draw_new_order_queue.append((order, offset))


def update_elevator_on_canvas(elevator, canvas):
    rect_top = canvas.coords(elevator.rectangle)[1]
    if rect_top != elevator.top:
        canvas.move(elevator.rectangle, 0, elevator.top - rect_top)


def rescheduler():
    while not finish:
        if all([ele.status == Elevator.STATUS_IDLE for ele in elevator_list]):
            pass



def main():
    global current_time
    master = Tk()
    canvas = Canvas(master, width=900, height=950)
    canvas.pack()
    draw_building(master, canvas)
    init_and_draw_elevators(canvas)
    draw_cabin(canvas)
    draw_counter(canvas)

    threads = []
    thread_order_gen = threading.Thread(target=order_generator_thread)
    thread_order_gen.start()
    threads.append(thread_order_gen)

    for ele in elevator_list:
        ele_thread = threading.Thread(target=ele.elevator_thread)
        ele_thread.start()
        threads.append(ele_thread)

    prev_finished_order_count = finished_order_count
    while finished_order_count < NUM_ORDER:
        redraw_waiting_orders(canvas)
        draw_new_order(canvas)

        for ele in elevator_list:
            update_elevator_on_canvas(ele, canvas)

        redraw_elevator_status(canvas)
        redraw_cabin(canvas)
        if finished_order_count != prev_finished_order_count:
            prev_finished_order_count = finished_order_count
            canvas.delete(canvas_counter)
            draw_counter(canvas)

        master.update()
        time.sleep(0.1)
        current_time += 0.1

    global finish
    finish = True

    for t in threads:
        t.join()

    # update UI after everything finished
    redraw_waiting_orders(canvas)
    draw_new_order(canvas)

    for ele in elevator_list:
        update_elevator_on_canvas(ele, canvas)

    redraw_elevator_status(canvas)
    redraw_cabin(canvas)
    canvas.delete(canvas_counter)
    draw_counter(canvas)

    # show result
    from tkinter import messagebox
    messagebox.showinfo("Title", "a Tk MessageBox")
    mainloop()


if __name__ == '__main__':
    main()
