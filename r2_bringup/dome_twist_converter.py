#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped
from std_msgs.msg import Float64MultiArray


class DomeTwistConverter(Node):
    """Converts Twist messages to Float64MultiArray for dome velocity control."""

    def __init__(self):
        super().__init__('dome_twist_converter')
        
        self.subscription = self.create_subscription(
            TwistStamped,
            'cmd_vel_dome',
            self.twist_callback,
            10
        )
        
        self.publisher = self.create_publisher(
            Float64MultiArray,
            'dome_controller/commands',
            10
        )
        
        self.get_logger().info('Dome Twist Converter initialized')

    def twist_callback(self, msg: TwistStamped):
        """Convert Twist message to Float64MultiArray."""
        # Use linear.x velocity for dome rotation
        cmd_array = Float64MultiArray()
        cmd_array.data = [msg.twist.linear.x]
        self.publisher.publish(cmd_array)


def main(args=None):
    rclpy.init(args=args)
    node = DomeTwistConverter()
    rclpy.spin(node)
    self.get_logger().info('Shutting down Dome Twist Converter')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
