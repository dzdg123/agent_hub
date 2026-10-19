# 文本位置记录
offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。
文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。
重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。
