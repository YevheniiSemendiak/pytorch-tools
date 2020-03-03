import torch.nn as nn
from pytorch_tools.modules import bn_from_name
from pytorch_tools.modules.residual import conv1x1
from pytorch_tools.modules.decoder import UnetDecoderBlock
from pytorch_tools.utils.misc import initialize
from .base import EncoderDecoder
from .encoders import get_encoder


class UnetCenterBlock(UnetDecoderBlock):
    def forward(self, x):
        self.block(x)


class UnetDecoder(nn.Module):
    def __init__(
        self,
        encoder_channels,
        decoder_channels=(256, 128, 64, 32, 16),
        final_channels=1,
        center=False,
        drop_rate=0,
        **bn_params,  # norm layer, norm_act
    ):

        super().__init__()
        if center:
            channels = encoder_channels[0]
            self.center = UnetCenterBlock(channels, channels)
        else:
            self.center = None

        in_channels = self.compute_channels(encoder_channels, decoder_channels)
        out_channels = decoder_channels

        self.layer1 = UnetDecoderBlock(in_channels[0], out_channels[0], **bn_params)
        self.layer2 = UnetDecoderBlock(in_channels[1], out_channels[1], **bn_params)
        self.layer3 = UnetDecoderBlock(in_channels[2], out_channels[2], **bn_params)
        self.layer4 = UnetDecoderBlock(in_channels[3], out_channels[3], **bn_params)
        self.layer5 = UnetDecoderBlock(in_channels[4], out_channels[4], **bn_params)
        self.dropout = nn.Dropout2d(drop_rate, inplace=True)
        self.final_conv = conv1x1(out_channels[4], final_channels)

        initialize(self)

    def compute_channels(self, encoder_channels, decoder_channels):
        channels = [
            encoder_channels[0] + encoder_channels[1],
            encoder_channels[2] + decoder_channels[0],
            encoder_channels[3] + decoder_channels[1],
            encoder_channels[4] + decoder_channels[2],
            0 + decoder_channels[3],
        ]
        return channels

    def forward(self, x):
        encoder_head = x[0]
        skips = x[1:]

        if self.center:
            encoder_head = self.center(encoder_head)

        x = self.layer1([encoder_head, skips[0]])
        x = self.layer2([x, skips[1]])
        x = self.layer3([x, skips[2]])
        x = self.layer4([x, skips[3]])
        x = self.layer5([x, None])
        x = self.dropout(x)
        x = self.final_conv(x)

        return x


class Unet(EncoderDecoder):
    """Unet_ is a fully convolution neural network for image semantic segmentation
    Args:
        encoder_name (str): name of classification model (without last dense layers) used as feature
            extractor to build segmentation model.
        encoder_weights (str): one of ``None`` (random initialization), ``imagenet`` (pre-training on ImageNet).
        decoder_channels (List[int]): list of numbers of ``Conv2D`` layer filters in decoder blocks
        num_classes (int): a number of classes for output (output shape - ``(batch, classes, h, w)``).
        center (bool): if ``True`` add ``Conv2dReLU`` block on encoder head (useful for VGG models)
        drop_rate (float): Probability of spatial dropout on last feature map
        norm_layer (str): Normalization layer to use. One of 'abn', 'inplaceabn'. The inplace version lowers memory
            footprint. But increases backward time. Defaults to 'abn'.
        norm_act (str): Activation for normalizion layer. 'inplaceabn' doesn't support `ReLU` activation.
    Returns:
        ``torch.nn.Module``: **Unet**
    .. _Unet:
        https://arxiv.org/pdf/1505.04597
    """

    def __init__(
        self,
        encoder_name="resnet34",
        encoder_weights="imagenet",
        decoder_channels=(256, 128, 64, 32, 16),
        num_classes=1,
        center=False,  # usefull for VGG models
        drop_rate=0,
        norm_layer="abn",
        norm_act="relu",
        **encoder_params,
    ):
        encoder = get_encoder(
            encoder_name,
            norm_layer=norm_layer,
            norm_act=norm_act,
            encoder_weights=encoder_weights,
            **encoder_params,
        )
        decoder = UnetDecoder(
            encoder_channels=encoder.out_shapes,
            decoder_channels=decoder_channels,
            final_channels=num_classes,
            center=center,
            drop_rate=drop_rate,
            norm_layer=bn_from_name(norm_layer),
            norm_act=norm_act,
        )

        super().__init__(encoder, decoder)
        self.name = f"u-{encoder_name}"
