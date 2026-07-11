"""
    为整个工程提供统一的绝对路径
"""

import os

def get_project_root() -> str:
    """
        获取工程所在的根目录
        :return:字符串根目录
    """

    # 当前文件: <root>/src/utils/path_tool.py → 上溯两级到项目根目录
    current_file = os.path.abspath(__file__)
    utils_dir = os.path.dirname(current_file)       # .../src/utils
    src_dir = os.path.dirname(utils_dir)            # .../src
    project_root = os.path.dirname(src_dir)         # .../ (项目根)
    return project_root

def get_abs_path(relative_path: str) -> str:
    """
        相对路径传递，得到绝对路径
        :param relative_path: 相对路径
        :return 绝对路径
    """
    project_root = get_project_root()
    # 把 project_root（基础路径）和 relative_path（相对路径）智能地拼接成一个完整的路径。
    return os.path.join(project_root, relative_path)



if __name__ == "__main__":
    print(get_project_root())
    # print(get_abs_path("mcp_server/tools/calculator.py"))