import numpy as np
import torch
from typing import Optional, Tuple


def compute_mask_indices(
    shape: Tuple[int, int],
    padding_mask: Optional[torch.Tensor],
    mask_prob: float,
    mask_length: int,
    mask_type: str = "static",
    mask_other: float = 0.0,
    min_masks: int = 0,
    no_overlap: bool = False,
    min_space: int = 0,
) -> np.ndarray:
    """
    Computes random mask spans for a given shape

    Args:
        shape: the the shape for which to compute masks.
            should be of size 2 where first element is batch size and 2nd is timesteps
        padding_mask: optional padding mask of the same size as shape, which will prevent masking padded elements
        mask_prob: probability for each token to be chosen as start of the span to be masked. this will be multiplied by
            number of timesteps divided by length of mask span to mask approximately this percentage of all elements.
            however due to overlaps, the actual number will be smaller (unless no_overlap is True)
        mask_type: how to compute mask lengths
            static = fixed size
            uniform = sample from uniform distribution [mask_other, mask_length*2]
            normal = sample from normal distribution with mean mask_length and stdev mask_other. mask is min 1 element
            poisson = sample from possion distribution with lambda = mask length
        min_masks: minimum number of masked spans
        no_overlap: if false, will switch to an alternative recursive algorithm that prevents spans from overlapping
        min_space: only used if no_overlap is True, this is how many elements to keep unmasked between spans
    """
    
    bsz, all_sz = shape
    mask = np.full((bsz, all_sz), False)
    
    # Convert mask_prob to a NumPy array
    mask_prob = np.array(mask_prob)
    
    # Calculate all_num_mask for each element in the batch
    all_num_mask = np.floor(mask_prob * all_sz / float(mask_length) + np.random.rand(bsz)).astype(int)
    
    # Apply the max operation with min_masks for each element
    all_num_mask = np.maximum(min_masks, all_num_mask)

    mask_idcs = []
    for i in range(bsz):
        if padding_mask is not None:
            sz = padding_mask[i].long().sum().item()
            num_mask = int(
                # add a random number for probabilistic rounding
                mask_prob[i] * sz / float(mask_length)
                + np.random.rand()
            )
            num_mask = max(min_masks, num_mask)
        else:
            sz = all_sz
            num_mask = all_num_mask[i]

        if mask_type == "static":
            lengths = np.full(num_mask, mask_length)
        elif mask_type == "uniform":
            lengths = np.random.randint(mask_other, mask_length * 2 + 1, size=num_mask)
        elif mask_type == "normal":
            lengths = np.random.normal(mask_length, mask_other, size=num_mask)
            lengths = [max(1, int(round(x))) for x in lengths]
        elif mask_type == "poisson":
            lengths = np.random.poisson(mask_length, size=num_mask)
            lengths = [int(round(x)) for x in lengths]
        else:
            raise Exception("unknown mask selection " + mask_type)

        if sum(lengths) == 0:
            lengths[0] = min(mask_length, sz - 1)

        if no_overlap:
            mask_idc = []

            def arrange(s, e, length, keep_length):
                span_start = np.random.randint(s, e - length)
                mask_idc.extend(span_start + i for i in range(length))

                new_parts = []
                if span_start - s - min_space >= keep_length:
                    new_parts.append((s, span_start - min_space + 1))
                if e - span_start - keep_length - min_space > keep_length:
                    new_parts.append((span_start + length + min_space, e))
                return new_parts

            parts = [(0, sz)]
            min_length = min(lengths)
            for length in sorted(lengths, reverse=True):
                lens = np.fromiter(
                    (e - s if e - s >= length + min_space else 0 for s, e in parts),
                    int,
                )
                l_sum = np.sum(lens)
                if l_sum == 0:
                    break
                probs = lens / np.sum(lens)
                c = np.random.choice(len(parts), p=probs)
                s, e = parts.pop(c)
                parts.extend(arrange(s, e, length, min_length))
            mask_idc = np.asarray(mask_idc)
        else:
            min_len = min(lengths)
            if sz - min_len <= num_mask:
                min_len = sz - num_mask - 1

            mask_idc = np.random.choice(sz - min_len, num_mask, replace=False)

            mask_idc = np.asarray(
                [
                    mask_idc[j] + offset
                    for j in range(len(mask_idc))
                    for offset in range(lengths[j])
                ]
            )

        mask_idcs.append(np.unique(mask_idc[mask_idc < sz]))
    # min_len = min([len(m) for m in mask_idcs])
    # print(mask_idcs)
    for i, mask_idc in enumerate(mask_idcs):
        # if len(mask_idc) > min_len:
            # mask_idc = np.random.choice(mask_idc, min_len, replace=False)
        mask[i, mask_idc] = True

    return torch.tensor(mask)


if __name__ == '__main__':
    padding_mask = torch.ones(4, 500)
    padding_mask[0, 400:500] = 0
    padding_mask[1, 450:500] = 0
    mask = compute_mask_indices(
        shape=[4, 500],
        padding_mask=padding_mask,
        mask_prob=[0.5, 0.5, 0.65, 0.65],
        mask_length=10,
        mask_type="static",
        mask_other=0.0,
        min_masks=1,
        no_overlap=False,
        min_space=0,
    )
    print(mask)
    print(mask.sum(dim=1))