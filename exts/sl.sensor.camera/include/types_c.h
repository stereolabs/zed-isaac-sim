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

    /**
     * @brief Status returned by the sim-streamer entry points (init_streamer / stream_* / ingest_imu).
     *
     * 0 is success, positive values are errors, negative values are warnings (streaming continues).
     */
    enum class SIM_STREAMER_STATUS : int
    {
        /** The frame arrived faster than the configured FPS and was skipped. Benign. */
        FRAME_DROPPED = -1,
        SUCCESS = 0,
        /** Unspecified failure. */
        FAILURE = 1,
        /** The serial number is not a valid virtual camera. */
        INVALID_SERIAL_NUMBER = 2,
        /** A streamer with this id already exists. */
        STREAMER_ALREADY_CREATED = 3,
        /** Unexpected error while creating or opening the streamer. */
        INTERNAL_ERROR = 4,
        /** The streaming port must be even. */
        INVALID_PORT = 5,
        /** The streaming session could not be created on the port; it is likely already in use. */
        PORT_UNAVAILABLE = 6,
        /** The hardware video encoder could not be loaded; check the GPU and its driver. */
        ENCODER_LOAD_FAILED = 7,
        /** The hardware video encoder rejected the configuration (codec / resolution / FPS). */
        ENCODER_CREATION_FAILED = 8,
        /** Stream or ingest call on an unknown streamer id, or before a successful init. */
        STREAMER_NOT_OPENED = 9,
        /** Null buffer, or a call that does not match the streamer configuration. */
        INVALID_INPUT = 10,
        /** The frame could not be encoded or sent. */
        ENCODING_FAILED = 11,
        /** Returned by the loader when the library or a symbol is missing.
         *  Never returned by the library itself. */
        LIB_NOT_LOADED = 100,
    };

    inline const char* toString(SIM_STREAMER_STATUS status)
    {
        switch (status)
        {
        case SIM_STREAMER_STATUS::FRAME_DROPPED: return "FRAME_DROPPED";
        case SIM_STREAMER_STATUS::SUCCESS: return "SUCCESS";
        case SIM_STREAMER_STATUS::FAILURE: return "FAILURE";
        case SIM_STREAMER_STATUS::INVALID_SERIAL_NUMBER: return "INVALID_SERIAL_NUMBER";
        case SIM_STREAMER_STATUS::STREAMER_ALREADY_CREATED: return "STREAMER_ALREADY_CREATED";
        case SIM_STREAMER_STATUS::INTERNAL_ERROR: return "INTERNAL_ERROR";
        case SIM_STREAMER_STATUS::INVALID_PORT: return "INVALID_PORT";
        case SIM_STREAMER_STATUS::PORT_UNAVAILABLE: return "PORT_UNAVAILABLE";
        case SIM_STREAMER_STATUS::ENCODER_LOAD_FAILED: return "ENCODER_LOAD_FAILED";
        case SIM_STREAMER_STATUS::ENCODER_CREATION_FAILED: return "ENCODER_CREATION_FAILED";
        case SIM_STREAMER_STATUS::STREAMER_NOT_OPENED: return "STREAMER_NOT_OPENED";
        case SIM_STREAMER_STATUS::INVALID_INPUT: return "INVALID_INPUT";
        case SIM_STREAMER_STATUS::ENCODING_FAILED: return "ENCODING_FAILED";
        case SIM_STREAMER_STATUS::LIB_NOT_LOADED: return "LIB_NOT_LOADED";
        }
        return "UNKNOWN";
    }

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

        int gop_size = -1; // in frames

        // When true, dataPtrLeft/Right are CUDA device pointers handed straight to the
        // encoder (no host copy). Honored only on the RGBA/BGRA network path.
        bool gpu_input = false;
        bool stream_depth = false;
        int depth_width = 0;
        int depth_height = 0;
        int depth_bitrate = 0;
    };

    enum class SIM_LENS_TYPE {
        WIDE,
        NARROW,
        FISHEYE
    };

    struct SimCameraInfo {
        int serial_number;
        int model;
        SIM_LENS_TYPE lens_type;
    };

}

#endif