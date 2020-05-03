#include <iostream>
#include <string>
#include <WS2tcpip.h>
#include <vector>
#include <chrono>
#include <thread>
#include <mutex>
#include <map>
#include <random>
#include <sstream>
#pragma comment(lib, "ws2_32.lib")
using namespace std;

// config
int PORT = 54000;
int MAX_FLOOR = 30;
int MIN_FLOOR = -4;
int NUM_FLOOR = (MAX_FLOOR - MIN_FLOOR + 1);  // including ground floor
int NUM_ELEVATOR = 2;
int ELEVATOR_CAPACITY = 20;
int NUM_ORDER = 100;

// speed config
// elevator speed is one pixel per loop
std::chrono::milliseconds ELEVATOR_MOVE_INTERVAL(5);  // elevator moves by one pixel
std::chrono::milliseconds LOADING_UNLOADING_TIME(1000);  // time in milliseconds that loading or unloading passengers takes
std::chrono::milliseconds ORDER_GENERATE_INTERVAL(1000);  // time in milliseconds between new orders


// graphic config
#define ELEVATOR_WIDTH 50
#define ELEVATOR_HEIGHT 25
#define ORDER_WIDTH 21

// canvas position
#define LEFT_P 70
#define TOP_P 60

#define GROUND_FLOOR_TOP (TOP_P + MAX_FLOOR * ELEVATOR_HEIGHT)
#define MIN_FLOOR_TOP (TOP_P + (MAX_FLOOR - MIN_FLOOR) * ELEVATOR_HEIGHT)


class Order {
public:
	int from_floor;
	int status;
	int to_floor;
	std::chrono::time_point<std::chrono::system_clock> create_time;
	std::chrono::time_point<std::chrono::system_clock> load_time;
	std::chrono::time_point<std::chrono::system_clock> unload_time;
	int id;
	Order(int from_floor, int to_floor, std::chrono::time_point<std::chrono::system_clock> create_time, int id) {
		this->from_floor = from_floor;
		this->to_floor = to_floor;
		this->create_time = create_time;
		this->id = id;
		this->status = 0;
	}
};

// global variables
bool finish = false;
int finished_order_count = 0;
int cur_time = 0;
vector<Order*> finished_orders;
mutex finished_orders_lock;
mutex finished_order_count_lock;
map<int, mutex*> waiting_orders_lock;
map<int, vector<Order*>> waiting_orders;

class Elevator {
public:
	unsigned int capacity;
	int index;
	int top;
	int floor;
	vector<Order*> cabin;

	int status = 3;
	int UI_status = 3;

	int going_up_target_floor=999;
	int going_down_target_floor=999;

	Elevator(int capacity, int index, int top, int floor) {
		this->capacity = capacity;
		this->index = index;
		this->top = top;
		this->floor = floor;
		this->status = 3;
		this->UI_status = 3;
	}

	void set_going_down_target_floor(int floor) {
		if (this->going_down_target_floor == 999) {
			this->going_down_target_floor = floor;
		}
		else {
			this->going_down_target_floor = min(this->going_down_target_floor, floor);
		}
	}

	void set_going_up_target_floor(int floor) {
		if (this->going_up_target_floor == 999) {
			this->going_up_target_floor = floor;
		}
		else {
			this->going_up_target_floor = max(this->going_up_target_floor, floor);
		}
	}

	int get_current_floor() {
		if ((this->top - TOP_P) % ELEVATOR_HEIGHT != 0) {
			return this->floor;
		}

		auto floor_id = int((top - TOP_P) / ELEVATOR_HEIGHT);
		return MAX_FLOOR - floor_id;
	}

	void going_up() {
		auto cur_floor = this->get_current_floor();

		// reach new floor
		if (this->floor != cur_floor) {
			this->floor = cur_floor;
			this->unload();
			this->load();
		}

		// reach target floor, go to idle or go down
		if (this->floor == this->going_up_target_floor || this->floor == MAX_FLOOR) {
			if (this->cabin.size() != 0) {
				throw exception("bug");
			}

			this->going_up_target_floor = 999;

			if (this->going_down_target_floor != 999) {
				this->status = 2;
				this->UI_status = 2;
				this->load();
			}
			else {
				this->status = 2;
				this->UI_status = 2;
				this->load();
				if (this->cabin.size() == 0) {
					// no orders, go to idle
					this->status = 3;
					this->UI_status = 3;
				}
			}
		}
		else {
			this->top -= 1;
		}
	}

	void going_down() {
		auto cur_floor = this->get_current_floor();

		// reach new floor
		if (this->floor != cur_floor) {
			this->floor = cur_floor;
			this->unload();
			this->load();
		}

		// reach target floor, go to idle or go up
		if (this->floor == this->going_down_target_floor || this->floor == MIN_FLOOR) {
			if (this->cabin.size() != 0) {
				throw exception("bug");
			}

			this->going_down_target_floor = 999;

			if (this->going_up_target_floor != 999) {
				this->status = 1;
				this->UI_status = 1;
				this->load();
			}
			else {
				this->status = 1;
				this->UI_status = 1;
				this->load();
				if (this->cabin.size() == 0) {
					// no orders, go to idle
					this->status = 3;
					this->UI_status = 3;
				}
			}
		}
		else {
			this->top += 1;
		}
	}

	void idle() {
		if (this->going_down_target_floor != 999) {
			this->status = 2;
			this->UI_status = 2;
			this->load();
		}
		else if (this->going_up_target_floor != 999) {
			this->status = 1;
			this->UI_status = 1;
			this->load();
		}
	}

	void unload() {
		this->UI_status = 5;
		auto cur_floor = this->get_current_floor();

		vector<Order*> new_cabin;
		vector<Order*> finished;
		for (auto order : this->cabin) {
			if (order->to_floor == cur_floor) {
				this->finish_order(order);
				order->status = 2;
				order->unload_time = chrono::system_clock::now();
				std::this_thread::sleep_for(LOADING_UNLOADING_TIME);
			}
			else {
				new_cabin.push_back(order);
			}
		}

		for (auto order : finished) {
			order->status = 4;
			finished_orders_lock.lock();
			finished_orders.push_back(order);
			finished_orders_lock.unlock();
		}

		this->cabin = new_cabin;
		this->UI_status = this->status;
	}

	void load() {
		this->UI_status = 4;
		auto cur_floor = this->get_current_floor();
		auto lock = waiting_orders_lock[cur_floor];
		lock->lock();

		auto orders = waiting_orders[cur_floor];
		vector<Order*> new_waiting_orders;
		int count = 0;

		for (auto order : orders) {
			// full
			if (this->cabin.size() >= this->capacity) {
				new_waiting_orders.push_back(order);
				continue;
			}

			if (order->to_floor > cur_floor && this->status == 1) {
				cabin.push_back(order);
				this->set_going_up_target_floor(order->to_floor);
				order->status = 1;
				order->load_time = chrono::system_clock::now();
				count += 1;
			}
			else if (order->to_floor < cur_floor && this->status == 2) {
				cabin.push_back(order);
				this->set_going_down_target_floor(order->to_floor);
				order->status = 1;
				order->load_time = chrono::system_clock::now();
				count += 1;
			}
			else {
				new_waiting_orders.push_back(order);
			}
		}
		waiting_orders.at(cur_floor) = new_waiting_orders;
		lock->unlock();

		if (count > 0) {
			std::this_thread::sleep_for(LOADING_UNLOADING_TIME);
			for (auto order : this->cabin) {
				order->status = 3;
			}
			// redraw waiting orders
			// redraw cabin
		}

		this->UI_status = this->status;
	}

	void finish_order(Order* order) {
		finished_order_count_lock.lock();
		finished_order_count += 1;
		finished_order_count_lock.unlock();
	}

	void elevator_thread() {

		cout << "elevator #" << this->index << " started" << endl;
		while (!finish) {
			if (this->status == 1) {
				this->going_up();
			}
			else if (this->status == 2) {
				this->going_down();
			}
			else {
				this->idle();
			}
			std::this_thread::sleep_for(ELEVATOR_MOVE_INTERVAL);
		}
	}

	void print_elevator() {
		auto ele = this;
		cout << "Elevator #" << ele->index << ": status: " << ele->status << " ui_status: " << ele->UI_status << " top: " << ele->top << " floor: " << ele->floor << endl;
		cout << "going_up_target: " << ele->going_up_target_floor << " going_down_target: " << ele->going_down_target_floor << endl;
		print_cabin();
	}

	void print_cabin() {
		cout << "Cabin: [";
		for (auto order : this->cabin) {
			cout << "(" << order->from_floor << ", " << order->to_floor << "), ";
		}
		cout << "]" << endl;
	}

};

vector<Elevator*> elevator_list;
void init() {
	for (int i = MIN_FLOOR; i <= MAX_FLOOR; i++) {
		auto p = pair<int, mutex*>(i, new mutex);
		waiting_orders_lock.insert(p);

		auto another_p = pair<int, vector<Order*>>(i, vector<Order*>());
		waiting_orders.insert(another_p);
	}

	for (int i = 0; i < NUM_ELEVATOR; i++) {
		elevator_list.push_back(new Elevator(ELEVATOR_CAPACITY, i, GROUND_FLOOR_TOP, 0));
	}
}

void schedule_order(Order* order, Elevator* ele) {
	if (order->from_floor > ele->floor) {
		ele->set_going_up_target_floor(order->from_floor);
	}
	else {
		ele->set_going_down_target_floor(order->from_floor);
	}
}


int calculate_elevator_order_distance(Order* order, Elevator* ele) {
	bool is_going_up = order->from_floor < order->to_floor;
	int distance;
	if (is_going_up) {
		if (ele->status == 1) {
			if (order->from_floor > ele->floor) {
				distance = order->from_floor - ele->floor;
			}
			else {
				distance = MAX_FLOOR - ele->floor + MAX_FLOOR - order->from_floor;
			}
		}
		else if (ele->status == 2) {
			distance = ele->floor - MIN_FLOOR + order->from_floor - MIN_FLOOR;
		}
		else {
			distance = abs(ele->floor - order->from_floor);
		}
	}
	else {
		if (ele->status == 2) {
			if (order->from_floor < ele->floor) {
				distance = ele->floor - order->from_floor;
			}
			else {
				distance = ele->floor - MIN_FLOOR + order->from_floor;
			}
		}
		else if (ele->status == 1) {
			distance = MAX_FLOOR - ele->floor + MAX_FLOOR - order->from_floor;
		}
		else {
			distance = abs(ele->floor - order->from_floor);
		}
	}

	return distance;
}

void order_scheduler() {
	while (!finish) {
		for (int floor = MIN_FLOOR; floor <= MAX_FLOOR; floor++) {
			for (auto order : waiting_orders[floor]) {
				int min_distance = calculate_elevator_order_distance(order, elevator_list[0]);
				Elevator* winner = elevator_list[0];
				for (unsigned int i = 1; i < elevator_list.size(); i++) {
					int distance = calculate_elevator_order_distance(order, elevator_list[i]);
					if (distance < min_distance) {
						winner = elevator_list[i];
						min_distance = distance;
					}
				}
				schedule_order(order, winner);
			}
		}
		std::this_thread::sleep_for(std::chrono::seconds(3));
	}
}

void OrderGenerator() {
	int counter = 0;
	int id = 0;
	while (counter < NUM_ORDER && !finish) {
		int from_floor = MIN_FLOOR + (rand() % static_cast<int>(MAX_FLOOR - MIN_FLOOR + 1));
		int to_floor = MIN_FLOOR + (rand() % static_cast<int>(MAX_FLOOR - MIN_FLOOR + 1));

		while (to_floor == from_floor) {
			to_floor = MIN_FLOOR + (rand() % static_cast<int>(MAX_FLOOR - MIN_FLOOR + 1));
		}

		auto cur_time = chrono::system_clock::now();
		auto order = new Order(from_floor, to_floor, cur_time, id);

		auto lock = waiting_orders_lock[from_floor];
		lock->lock();
		waiting_orders[from_floor].push_back(order);
		lock->unlock();

		// pick a closest elevator
		int min_distance = calculate_elevator_order_distance(order, elevator_list[0]);
		Elevator* winner = elevator_list[0];
		for (unsigned int i = 1; i < elevator_list.size(); i++) {
			int distance = calculate_elevator_order_distance(order, elevator_list[i]);
			if (distance < min_distance) {
				winner = elevator_list[i];
				min_distance = distance;
			}
		}
		schedule_order(order, winner);

		cout << "New order: " << order->from_floor << " " << order->to_floor << " picked ele: " << winner->index << endl;

		counter++;
		cout << "counter: " << counter << endl;
		id++;

		std::this_thread::sleep_for(ORDER_GENERATE_INTERVAL);
	}
}



string format_building() {

	stringstream ss;
	ss << MAX_FLOOR << "," <<
		MIN_FLOOR << "," <<
		NUM_FLOOR << "," <<
		NUM_ELEVATOR << "," <<
		ELEVATOR_CAPACITY << "," <<
		NUM_ORDER << "," <<
		ELEVATOR_WIDTH << "," <<
		ELEVATOR_HEIGHT << "," <<
		ORDER_WIDTH << "," <<
		LEFT_P << "," <<
		TOP_P << ",";
	return ss.str();
}

string format_memeory() {
	stringstream ss;

	for (auto ele : elevator_list) {
		ss << ele->index << "," <<
			ele->top << "," <<
			ele->UI_status << "," <<
			ele->cabin.size() << ",";
		for (auto order : ele->cabin) {
			ss << order->from_floor << ",";
			ss << order->to_floor << ",";
			ss << order->status<< ",";
		}
	}

	ss << finished_order_count << ",";

	for (int i = MIN_FLOOR; i <= MAX_FLOOR; i++) {
		auto floor_orders = waiting_orders[i];
		ss << floor_orders.size() << ",";
		for (auto order : floor_orders) {
			ss << order->to_floor << ",";
		}
	}
	return ss.str();
}


void start_serving() {
	//initialize winsock
	WSADATA wsData;
	WORD ver = MAKEWORD(2, 2);
	int wsOK = WSAStartup(ver, &wsData);
	if (wsOK != 0) {
		cerr << "Can't Initialize winsock! Quitting" << endl;
		WSACleanup();
		return;
	}
	//Create a socket
	SOCKET listening = socket(AF_INET, SOCK_STREAM, 0);
	if (listening == INVALID_SOCKET) {//-1
		cerr << "Can't create a socket" << endl;
	}
	//Bind the ip address and port to a socket
	sockaddr_in hint;
	hint.sin_family = AF_INET;
	hint.sin_port = htons(PORT);
	hint.sin_addr.s_addr = INADDR_ANY; //inet_pton ... also work
	bind(listening, (sockaddr*)&hint, sizeof(hint));
	listen(listening, SOMAXCONN);


	// serve
	while (true) {
		cout << "Waiting to accept" << endl;

		sockaddr_in client;
		int clientsize = sizeof(client);
		SOCKET clientSocket = accept(listening, (sockaddr*)&client, &clientsize);//actual socket for communicaitons
		char host[NI_MAXHOST]; //client's remote name
		char service[NI_MAXSERV]; //service (i.e., port) the client is connected on
		ZeroMemory(host, NI_MAXHOST);
		ZeroMemory(service, NI_MAXSERV);
		if (getnameinfo((sockaddr*)&client, sizeof(client), host, NI_MAXHOST, service,
			NI_MAXSERV, 0) == 0) {
			cout << host << "connected on port " << service << endl;
		}
		else {
			inet_ntop(AF_INET, &client.sin_addr, host, NI_MAXHOST);
			//opposite to inet_pton
			cout << host << " connected on port " <<
				ntohs(client.sin_port) << endl;//opposite to htons
		}
		//close listening socket
		//closesocket(listening);
		//while loop; accept and echo message back to client

		bool is_first = true;
		char buf[4096];
		while (true) {
			ZeroMemory(buf, 4096);
			//wait for client to send data
			int bytesReceived = recv(clientSocket, buf, 4096, 0);
			if (bytesReceived == SOCKET_ERROR) {
				cerr << "Error in recv(). Quitting" << endl;
				closesocket(clientSocket);
				WSACleanup();
				finish = true;
				return;
			}
			if (bytesReceived == 0) {
				cout << "client disconnected " << endl;
				cout << "closing server" << endl;
				closesocket(clientSocket);
				WSACleanup();
				finish = true;
				return;
			}

			if (is_first) {
				auto building_info = format_building();
				send(clientSocket, building_info.c_str(), building_info.length() + 1, 0);
				is_first = false;
			}
			else {
			    auto info = format_memeory();
				send(clientSocket, info.c_str(), info.length() + 1, 0);
			}
		}
		closesocket(clientSocket);
		std::this_thread::sleep_for(std::chrono::milliseconds(1000));
	}
	cout << "TCP server exited !!!" << endl;
	//close the socket
	//cleanup winsock
	WSACleanup();
}


int main(int argc, char** argv) {
	// load args
	if (argc == 9) {
		MAX_FLOOR = std::atoi(argv[1]);
		MIN_FLOOR = std::atoi(argv[2]);
		NUM_ELEVATOR = std::atoi(argv[3]);
		ELEVATOR_CAPACITY = std::atoi(argv[4]);
		NUM_ORDER = std::atoi(argv[5]);
		PORT = std::atoi(argv[6]);
		int order_interval = std::atoi(argv[7]);
		int loading_unloading = std::atoi(argv[8]);
		ORDER_GENERATE_INTERVAL = std::chrono::milliseconds(order_interval);
		LOADING_UNLOADING_TIME = std::chrono::milliseconds(loading_unloading);

        cout << "!!!!!!!!!!!!!!!!!" << endl;
		cout << MAX_FLOOR << " "
			<< MIN_FLOOR << " "
			<< NUM_ELEVATOR << " "
			<< ELEVATOR_CAPACITY << " "
			<< NUM_ORDER << " "
			<< order_interval << " "
			<< loading_unloading << " "
			<< PORT << endl;
	}

	init();

	vector<thread> ele_threads;

	for (auto ele : elevator_list) {
		ele_threads.push_back(thread(&Elevator::elevator_thread, ele));
	}

	auto gen = (thread(OrderGenerator));

	auto server = (thread(start_serving));
	auto scheduler = (thread(order_scheduler));


	while (!finish) {
		// cout << "finished_order_count: " << finished_order_count << endl;
		for (auto ele : elevator_list) {
			ele->print_elevator();
		}
		cout << endl << endl;
		if (finished_order_count >= NUM_ORDER) {
			finish = true;
			break;
		}
		std::this_thread::sleep_for(std::chrono::milliseconds(1000));
	}


	for (int i = 0; i < ele_threads.size(); i++) {
		ele_threads[i].join();
	}

	cout << "finished_orders len: " << finished_orders.size() << endl;

	gen.join();
	scheduler.join();
	server.join();

	cout << "server exited" << endl;
	return 0;
}