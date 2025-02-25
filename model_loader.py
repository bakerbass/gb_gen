import time
from transformers import AutoModelForCausalLM
from torch.cuda import is_available

SMALL_MODEL = 'stanford-crfm/music-small-800k'     # faster inference, worse sample quality
MEDIUM_MODEL = 'stanford-crfm/music-medium-800k'   # slower inference, better sample quality
LARGE_MODEL = 'stanford-crfm/music-large-800k'     # slowest inference, best sample quality

def load_model(model_size='large'):
    """
    Load the anticipatory music transformer model.

    :param model_size: Size of the model to load. Options are 'small', 'medium', 'large'.
    :return: Loaded model.
    """
    model_map = {
        'small': SMALL_MODEL,
        'medium': MEDIUM_MODEL,
        'large': LARGE_MODEL
    }

    model_name = model_map.get(model_size, LARGE_MODEL)

    start = time.time()
    if is_available():
        print("CUDA is available. Using GPU.")
        model = AutoModelForCausalLM.from_pretrained(model_name).cuda()
    else:
        print("CUDA is not available. Using CPU.")
        model = AutoModelForCausalLM.from_pretrained(model_name)
    end = time.time()

    print(f"Model '{model_name}' loaded in {end - start} seconds")
    return model