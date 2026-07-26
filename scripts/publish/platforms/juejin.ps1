function Invoke-JuejinPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "juejin"
        Url = "https://juejin.cn/editor/drafts/new?v=2"
        CoverRatio = "16:9"
        EntryHints = @("写文章", "编辑器", "发布", "草稿", "分类", "标签", "摘要")
        ManualBeforeDraft = ""
        PreClickTexts = @()
        OpenSettingsTexts = @("发布")
        CoverClickTexts = @("上传封面", "添加封面", "添加文章封面")
        SaveDraftTexts = @()
        SaveOptional = $true
        PublishTexts = @("确定并发布", "确认发布")
        Selectors = [pscustomobject]@{
            title = @(
                "input[placeholder*='输入文章标题']",
                "textarea[placeholder*='输入文章标题']",
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']"
            )
            body = @(
                ".bytemd-editor textarea",
                ".CodeMirror textarea",
                ".cm-content",
                ".ProseMirror",
                "textarea[placeholder*='请输入正文']",
                "[contenteditable='true']"
            )
            summary = @(
                "textarea[placeholder*='摘要']",
                "textarea[placeholder*='编辑摘要']",
                "input[placeholder*='摘要']"
            )
            topics = @()
            tags = @(
                "input[placeholder*='标签']",
                "input[placeholder*='搜索标签']",
                "input[placeholder*='添加标签']"
            )
            hashtags = @()
        }
    }

    Invoke-GenericPlatform $Context $spec $Pack
}
