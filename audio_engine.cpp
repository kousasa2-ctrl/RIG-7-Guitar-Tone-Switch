// audio_engine.cpp
// Компиляция: g++ -std=c++17 -O2 -o audio_engine.exe audio_engine.cpp -lportaudio -lpthread -lasio
#include <asio.hpp>
#include <portaudio.h>
#include <thread>
#include <vector>
#include <atomic>
#include <iostream>
#include <mutex>
#include <chrono>
#include <cstring>

#define DEFAULT_SAMPLE_RATE 44100
#define MIN_BUFFER 64
#define MAX_BUFFER 1024

std::atomic<bool> running(true);
std::mutex audio_mutex;
std::vector<float> net_in_buffer(MAX_BUFFER, 0.0f);
std::vector<float> net_out_buffer(MAX_BUFFER, 0.0f);
std::atomic<int> current_buffer_size(256);

void adjust_buffer_on_network(int rtt_ms) {
    // Простая адаптация: если rtt > 100мс — увеличить буфер, если < 40мс — уменьшить
    int buf = current_buffer_size.load();
    if (rtt_ms > 100 && buf < MAX_BUFFER) current_buffer_size = buf * 2 > MAX_BUFFER ? MAX_BUFFER : buf * 2;
    if (rtt_ms < 40 && buf > MIN_BUFFER) current_buffer_size = buf / 2 < MIN_BUFFER ? MIN_BUFFER : buf / 2;
}

void udp_receive(asio::ip::udp::socket& sock, int port) {
    while (running) {
        asio::ip::udp::endpoint sender;
        std::vector<char> recv_buf(MAX_BUFFER * sizeof(float));
        size_t len = sock.receive_from(asio::buffer(recv_buf), sender);
        int bufsize = current_buffer_size.load();
        if (len == bufsize * sizeof(float)) {
            std::lock_guard<std::mutex> lock(audio_mutex);
            memcpy(net_in_buffer.data(), recv_buf.data(), len);
        }
    }
}

void udp_send(asio::ip::udp::socket& sock, asio::ip::udp::endpoint& target) {
    while (running) {
        int bufsize = current_buffer_size.load();
        std::vector<float> out;
        {
            std::lock_guard<std::mutex> lock(audio_mutex);
            out.assign(net_out_buffer.begin(), net_out_buffer.begin() + bufsize);
        }
        sock.send_to(asio::buffer(out), target);
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}

static int audio_callback(const void*, void* output, unsigned long frameCount,
                          const PaStreamCallbackTimeInfo*, PaStreamCallbackFlags, void*) {
    int bufsize = current_buffer_size.load();
    if (frameCount > bufsize) frameCount = bufsize;
    {
        std::lock_guard<std::mutex> lock(audio_mutex);
        memcpy(output, net_in_buffer.data(), frameCount * sizeof(float));
        memcpy(net_out_buffer.data(), output, frameCount * sizeof(float));
    }
    return paContinue;
}

int main(int argc, char* argv[]) {
    // Аргументы: <phone_ip> <phone_port> <local_port> <buffer_size>
    std::string phone_ip = argc > 1 ? argv[1] : "127.0.0.1";
    int phone_port = argc > 2 ? std::stoi(argv[2]) : 5556;
    int local_port = argc > 3 ? std::stoi(argv[3]) : 5555;
    int bufsize = argc > 4 ? std::stoi(argv[4]) : 256;
    if (bufsize < MIN_BUFFER) bufsize = MIN_BUFFER;
    if (bufsize > MAX_BUFFER) bufsize = MAX_BUFFER;
    current_buffer_size = bufsize;

    asio::io_context io;
    asio::ip::udp::socket sock(io, asio::ip::udp::endpoint(asio::ip::udp::v4(), local_port));
    asio::ip::udp::endpoint phone_endpoint(asio::ip::address::from_string(phone_ip), phone_port);

    std::thread recv_thr(udp_receive, std::ref(sock), local_port);
    std::thread send_thr(udp_send, std::ref(sock), std::ref(phone_endpoint));

    Pa_Initialize();
    PaStream* stream;
    Pa_OpenDefaultStream(&stream, 0, 1, paFloat32, DEFAULT_SAMPLE_RATE, bufsize, audio_callback, nullptr);
    Pa_StartStream(stream);

    std::cout << "[AudioEngine] Старт. Буфер: " << bufsize << " сэмплов. Для выхода — Enter.\n";
    std::cin.get();
    running = false;

    Pa_StopStream(stream);
    Pa_CloseStream(stream);
    Pa_Terminate();
    recv_thr.join();
    send_thr.join();
    return 0;
}