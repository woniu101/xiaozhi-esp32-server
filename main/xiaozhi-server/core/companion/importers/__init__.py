__all__ = ["DotSkillAdapter", "ManualYamlAdapter"]


def __getattr__(name):
    if name == "DotSkillAdapter":
        from .dot_skill import DotSkillAdapter

        return DotSkillAdapter
    if name == "ManualYamlAdapter":
        from .manual_yaml import ManualYamlAdapter

        return ManualYamlAdapter
    raise AttributeError(name)
