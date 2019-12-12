'''
Author: Haoran Chen
Date: 12/10/2019
'''
import tensorflow as tf
import tensorflow.keras.layers as layers
import tensorflow.keras.datasets.cifar10 as cifar10
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.activations import relu





class RCNN:
    def __init__(self, FILTERS, WEIGHT_DECAY, RATE):
        self.decay_rate = WEIGHT_DECAY
        self.filters = FILTERS
        self.rate = RATE

        def local_response_normalization(x):
            return tf.nn.local_response_normalization(
                x, FILTERS/16, alpha=0.001, beta=0.75)

        config1 = {'padding': 'same', 'activation': tf.nn.relu, 
                    'kernel_regularizer': tf.keras.regularizers.l2(WEIGHT_DECAY), 
                    'filters': FILTERS, 'kernel_size': 5}

        config2 = {'filters':FILTERS, 'kernel_size': 3, 'padding': 'same', 
                    'kernel_regularizer': tf.keras.regularizers.l2(WEIGHT_DECAY)}

        self.lrn = layers.Lambda(local_response_normalization)
        self.relu = layers.Lambda(lambda x: relu(x))

        self.layer1 = layers.Conv2D(**config1)
        self.layer1_pool = layers.MaxPool2D(3, 2, 'same')
        self.layer1_dp = layers.Dropout(self.rate)

        self.layer2_forward = layers.Conv2D(**config2)
        self.layer2_recurrent = layers.Conv2D(**config2, use_bias=False)
        self.layer2_pool = layers.MaxPool2D(3, 2, 'same')
        self.layer2_dp = layers.Dropout(self.rate)

        self.layer3_forward = layers.Conv2D(**config2)
        self.layer3_recurrent = layers.Conv2D(**config2, use_bias=False)
        self.layer3_pool = layers.MaxPool2D(3, 2, 'same')
        self.layer3_dp = layers.Dropout(self.rate)

        self.layer4_forward = layers.Conv2D(**config2)
        self.layer4_recurrent = layers.Conv2D(**config2, use_bias=False)
        self.layer4_pool = layers.MaxPool2D(3, 2, 'same')
        self.layer4_dp = layers.Dropout(self.rate)

        self.layer5_forward = layers.Conv2D(**config2)
        self.layer5_recurrent = layers.Conv2D(**config2, use_bias=False)
        self.layer5_gpool = layers.GlobalMaxPool2D()

        self.layer6_dense = layers.Dense(10, activation='softmax')


    def __call__(self, imgs, train=True, recur=3):
        x = self.layer1(imgs)
        x = self.layer1_pool(x)
        x = self.layer1_dp(x, training=train)

        x = self._recurrent_layer(
            x, self.layer2_forward, self.layer2_recurrent, recur, 
            self.layer2_pool, self.layer2_dp, train)

        x = self._recurrent_layer(
            x, self.layer3_forward, self.layer3_recurrent, recur, 
            self.layer3_pool, self.layer3_dp, train)

        x = self._recurrent_layer(
            x, self.layer4_forward, self.layer4_recurrent, recur, 
            self.layer4_pool, self.layer4_dp, train)

        x = self._recurrent_layer(
            x, self.layer5_forward, self.layer5_recurrent, recur, 
            self.layer5_gpool, None, train)

        y = self.layer6_dense(x)
        return y

    def _recurrent_layer(self, x, forward, recurrent, recur, pool, dp=None, train=True):
        x_forward = forward(x)
        x_iter = self.lrn(self.relu(x_forward))
        for _ in range(recur):
            x_iter = self.lrn(self.relu(layers.add([recurrent(x_iter), x_forward])))
        
        x = pool(x_iter)
        if dp:
           x = dp(x, training=train)
        return x


if __name__ == "__main__":
    tf.app.flags.DEFINE_string('name', 'rcnn', 'name of model')
    tf.app.flags.DEFINE_float('lr', 0.001, 'Learning rate of the model')
    tf.app.flags.DEFINE_float('drop', 0.1, 'Drop rate for dropout layers')
    tf.app.flags.DEFINE_integer('filters', 96, 'Filter number')
    tf.app.flags.DEFINE_float('wdecay', 0.0001, 'Weight Decay')
    flags = tf.app.flags.FLAGS

    data = cifar10.load_data()
    (train_data, train_labels), (test_data, test_labels) = data
    train_labels = to_categorical(train_labels)
    test_labels = to_categorical(test_labels)

    train_datagen = ImageDataGenerator(
        rotation_range=30, width_shift_range=0.1, height_shift_range=0.1, 
        zoom_range=0.1, horizontal_flip=True, rescale=1/255.)
    train_generator = train_datagen.flow(
        train_data[:-5000], train_labels[:-5000], batch_size=128)

    val_datagen = ImageDataGenerator(rescale=1/255.)
    val_generator = val_datagen.flow(train_data[-5000:], 
        train_labels[-5000:], batch_size=128, shuffle=False)
    
    test_datagen = ImageDataGenerator(rescale=1/255.)
    test_generator = test_datagen.flow(
        test_data, test_labels, batch_size=128, shuffle=False)

    rcnn = RCNN(flags.filters, flags.wdecay, flags.drop)
    input_tensor_train = tf.keras.Input(shape=(32, 32, 3))
    output_tensor_train = rcnn(input_tensor_train, True, 3)
    train_model = tf.keras.Model(input_tensor_train, output_tensor_train)
    callbacks_list = [
        tf.keras.callbacks.ModelCheckpoint(
            filepath='./model/%s-%d-%g-%g-%g-best.h5'%(
                flags.name, flags.filters, flags.lr, flags.wdecay, flags.drop), 
            monitor='val_acc', save_best_only=True), 
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor='val_acc', factor=0.1, patience=7, min_lr=flags.lr/1000.)]
    train_model.summary()
    train_model.compile(
        optimizer=tf.keras.optimizers.SGD(0.001, 0.9, nesterov=True), 
        loss='categorical_crossentropy', metrics=['acc'])

    history = train_model.fit_generator(
        train_generator, epochs=128, 
        validation_data=val_generator, max_queue_size=128, workers=2, 
        callbacks=callbacks_list)
    train_model.load_weights('./model/%s-%d-%g-%g-%g-best.h5'%(
                flags.name, flags.filters, flags.lr, flags.wdecay, flags.drop))
    test_result = train_model.evaluate_generator(test_generator)
    print(test_result)
