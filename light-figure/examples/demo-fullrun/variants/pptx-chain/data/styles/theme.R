# light-figure compiled theme（bundle f39c196b0510…）
# 期刊 Demo Journal (Nature Figure Guide anchors) 2026；
# 分类色板 PAL-OI-8@2002.1、连续色板 PAL-BATLOW@8.0。
# 本文件为样式编译的文本产物：R 线脚本只许消费本文件，不许散写刊规数值。

light_figure_categorical <- c("#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00", "#cc79a7", "#000000")
light_figure_sequential <- c("#011959", "#0d315d", "#114360", "#175262", "#226061", "#356a59", "#4d734d", "#677b3e", "#828231", "#a18a2b", "#c09036", "#dd954d", "#f29d6d", "#fca993", "#fdb4b6", "#fcc0d8", "#faccfa")

theme_light_figure <- function() {
  ggplot2::theme_minimal(base_size = 7.0,
                         base_family = "Arial") +
    ggplot2::theme(
      axis.title = ggplot2::element_text(size = 7.0),
      axis.text = ggplot2::element_text(size = 6.0),
      legend.text = ggplot2::element_text(size = 6.0),
      panel.grid.minor = ggplot2::element_blank())
}

scale_color_light_figure_d <- function(...) {
  ggplot2::scale_color_manual(values = light_figure_categorical, ...)
}
scale_fill_light_figure_d <- function(...) {
  ggplot2::scale_fill_manual(values = light_figure_categorical, ...)
}
scale_color_light_figure_seq <- function(...) {
  ggplot2::scale_color_gradientn(colours = light_figure_sequential, ...)
}
