"""
此模块定义了继承自基础Node的、具有特殊功能或配置的节点类型。
"""
from pathlib import Path
from .abstractions import Node

class FrrOspfNode(Node):
    """
    一个表示运行FRR OSPF的节点的类。
    它知道如何为自己生成FRR配置文件，并将其放置在正确的目录结构中。
    它也知道如何构建自己的Docker镜像。
    """
    def __init__(self, name: str, **kwargs):
        # 为FRR OSPF节点设置默认属性
        defaults = {
            'image': 'vortinet_frr', # 镜像标签由目录名决定
            'node_type': 'frr_ospf',
            'post_start_command': '/usr/lib/frr/frrinit.sh start',
            'build': {
                'path': './dockerfile/vortinet_frr',
                'dockerfile': 'Dockerfile'
            }
        }
        # 用户传入的kwargs可以覆盖默认值
        defaults.update(kwargs)
        # 调用父类的构造函数，但要确保父类的默认值不会覆盖我们的特定设置
        # 我们通过将 'build' 和 'image' 信息传递给父类来实现这一点
        super().__init__(name, **defaults)

    def generate_config(self, node_config_root: str):
        """
        在此节点专属的配置根目录中生成FRR所需的完整文件结构和配置文件。

        :param node_config_root: 主机上为该节点创建的配置根目录的绝对路径 (e.g., /path/to/runtime_configs/R1)。
        """
        # 创建FRR配置所需的目录结构: <node_config_root>/etc/frr/
        frr_config_dir = Path(node_config_root) / 'etc' / 'frr'
        frr_config_dir.mkdir(parents=True, exist_ok=True)

        # 1. 创建 daemons 文件，启用 ospfd
        daemons_path = frr_config_dir / 'daemons'
        with open(daemons_path, 'w') as f:
            # 默认关闭所有守护进程，只开启需要的
            daemons_content = [
                "zebra=yes", "bgpd=no", "ospfd=yes", "ospf6d=no",
                "ripd=no", "ripngd=no", "isisd=no", "pimd=no",
                "ldpd=no", "nhrpd=no", "eigrpd=no", "babeld=no",
                "sharpd=no", "staticd=no", "pbrd=no", "bfdd=no"
            ]
            f.write("\n".join(daemons_content) + "\n")

        # 2. 创建 vtysh.conf 文件
        vtysh_path = frr_config_dir / 'vtysh.conf'
        with open(vtysh_path, 'w') as f:
            f.write("service integrated-vtysh-config\n")

        # 3. 创建 frr.conf 文件，并宣告所有直连网络
        frr_conf_path = frr_config_dir / 'frr.conf'
        with open(frr_conf_path, 'w') as f:
            f.write(f"hostname {self.name}\n")
            f.write("log stdout\n")
            f.write("!\n")
            f.write("router ospf\n")
            # 动态宣告该节点所有接口所在的网络
            for iface in self.interfaces.values():
                if iface.link:
                    f.write(f" network {iface.link.subnet} area 0\n")
            f.write("!\n")
