

nbconvert:
	jupyter nbconvert --to script note_apx.ipynb

test:
	/Users/wpq/opt/miniconda3/envs/misc_impl/bin/python3 gpax_test.py -v

train_mnist:
	CUDA_VISIBLE_DEVICES=0 python flax_train_image_model.py \
		--config=flax_train_image_model_config.py:mnist

train_cifa10:
	CUDA_VISIBLE_DEVICES=0 python flax_train_image_model.py \
		--config=flax_train_image_model_config.py:cifar10 \
		--config.model='CNNMnist' \
		--config.n_epochs=50
	CUDA_VISIBLE_DEVICES=1 python flax_train_image_model.py \
		--config=flax_train_image_model_config.py:cifar10 \
		--config.model='ResNet18' \
		--config.n_epochs=50

train_cub200:
	CUDA_VISIBLE_DEVICES=0 python flax_train_image_model.py \
		--config=flax_train_image_model_config.py:cub200 \
		--config.model='ResNet18' \
		--config.n_epochs=100

pytest:
	python -m pytest -v -n 2 --durations=10

pytest_time:
	python -m pytest -v --durations=10
	python -m pytest --collect-only


create_env:
	conda env create -f mi_gp.yml

remove_env:
	conda env remove --name mi_gp

install_jax:
	# pip install --upgrade jax==0.2.3 jaxlib==0.1.56+cuda100 -f https://storage.googleapis.com/jax-releases/jax_releases.html
	# pip install flax==0.2.2
	# https://pypi.org/project/flax/#history
	# flax >0.3.0 requires jax>0.2.6

	pip install --upgrade jax jaxlib==0.1.66+cuda111 -f https://storage.googleapis.com/jax-releases/jax_releases.html
	pip install flax

install_torch:
	pip install torch==1.9.0+cu111 torchvision==0.10.0+cu111 -f https://download.pytorch.org/whl/torch_stable.html

install_pkg_via_pip:
	pip install -r requirements.txt

setup:
	create_env
	install_torch
	install_jax
	install_pkg_via_pip

autoremove:
	pip install pip-autoremove
	pip-autoremove jax jaxlib flax

uninstall_jax:
	pip install pip-autoremove
	pip-autoremove jax jaxlib -y

rsync_assets_r2l:
	rsync -a wasabi.csail.mit.edu:/data/vision/polina/scratch/wpq/github/misc_impl/gp/summary/assets/ summary/assets/

rsync_cub:
	rsync -a CUB_200_2011.tgz wpq@wasabi.csail.mit.edu:/data/vision/polina/scratch/wpq/github/misc_impl/gp/data/