#ifndef __TYPES_C_H__
#define __TYPES_C_H__

namespace sl
{
    enum class INPUT_FORMAT
    {
        RGB = 0,
        BGR = 1,
        YUV = 2
    };

    struct StreamingParameters
    {
        /**
         * @brief Streaming mode (gen 1 or gen 2)
         *
         */
        int mode = 1;
        /**
         * @brief imu to cam quaternion (IMAGE)
         *
         */
        float imu_cam_q[4] = { 0,0,0,1 };
        /**
         * @brief imu to cam translation (IMAGE)
         *
         */
        float imu_cam_t[3] = { 0,0,0 };
        /**
         * @brief Width of the image in pixels
         *
         */
        int image_width = 1920;

        /**
         * @brief Height of the image in pixels
         *
         */
        int image_height = 1200;

        /**
         * @brief Codec type, 0 for H264 (default), 1 for H265.
         *
         */
        int codec_type = 1;
        /**
         * @brief The streaming port
         *
         */
        unsigned short port = 30000;

        /**
         * @brief FPS Cap. Images at a higher frequency will be dropped.
         *
         */
        int fps = 30;

        /**
         * @brief Serial number of the camera
         *
         */
        int serial_number = 40976320;

        /**
         * @brief Specifies whether the streamed image data includes the Alpha channel
         *
         */
        bool alpha_channel_included = true;

        /**
         * @brief Specifies if the data is encoded as BGR or RGB
         *
         */
        INPUT_FORMAT input_format = INPUT_FORMAT::RGB;

        /**
         * @brief Defines whether the streamer should print status information
         *
         */
        bool verbose = true;
        /**
         * @brief Defines the transport layer mode
         * 0 = RTP only, 1 = IPC only, 2 = both
         *
         */
        int transport_layer_mode = 0;
        /**
         * @brief Bitrate in Kbps
         *
         */
        int bitrate = 8000; // in Kbps
        /**
         * @brief Size of each chunk in bytes
         *
         */
        unsigned short chunk_size = 4096; // in bytes
    };

}

#endif