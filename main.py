import os.path
import sys

import crawler

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    if len(sys.argv) > 1:
        url = sys.argv[1]
        save_path = os.path.curdir
        image_size = None

        if len(sys.argv) > 3:
            image_size = crawler.ImageSize(map(int, sys.argv[2:4]))
        else:
            if len(sys.argv) > 4:
                save_path = sys.argv[4]

        crawler.Crawler(url, save_path, image_size)
    else:
        print('egloos image crawler. You can download sorted images over specific size')
        print('')
        print('usage: [egloos post url] [image width] [image height] (save path)')
        print('\tpython main.py http://ehei.egloos.com/ 800 800')